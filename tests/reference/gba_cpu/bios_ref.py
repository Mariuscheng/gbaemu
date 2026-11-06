"""BIOS：開機 HLE + SWI 函式 HLE（對照 GBATEK 第 16 章）。

SWI 註解欄位（GBATEK"How BIOS Processes SWIs"）：真 BIOS 讀 [LR-2]——
  ARM  ：LR=指令+4 → 取指令 bit16-23（即 `SWI NNNNNN` 的 nn<<16 編碼）
  Thumb：LR=指令+2 → 取指令 bit0-7
本 HLE 的 cpu.swi() 收的已是「註解 byte」，由 arm.py/thumb.py 依此規則抽取。

純數學／查表 helper（Div、ArcTan、Affine、Midi）已整併到
:mod:`gbaemu.hle.swi_math`，本檔只保留 SWI dispatch 與解壓縮。
"""
import math
import logging

log = logging.getLogger("pygba")   # 診斷訊息預設靜音；logging.basicConfig(level=logging.INFO) 可開啟


from gbaemu.hle.swi_math import (
    SINTAB as _SINTAB,
    biosatan2 as _biosatan2,
    biostan as _biostan,
    midi_val as _midi_val,
    q8 as _q8,
    s16 as _s16,
    sdiv as _sdiv,
    signed32 as _signed32,
)


def _flush16(bus, dst, buf):
    """把解壓縮緩衝以 16-bit 單位寫入（VRAM 不可 byte 寫入，須 halfword）。
    尾端單 byte 以「保留後一 byte」的半字改寫，不越界。"""
    n = len(buf)
    i = 0
    while i + 1 < n:
        bus.write16(dst + i, buf[i] | (buf[i + 1] << 8))
        i += 2
    if i < n:                      # 尾端單 byte：保留 [dst+i+1] 原值一起寫
        nxt = bus.read8(dst + i + 1)
        bus.write16(dst + i, buf[i] | (nxt << 8))


# BIOS ROM 內建的 Nintendo logo（00003290h 起 156 bytes）
# 真機開機時，BIOS 會與卡匣表頭 004h..09Fh 的 156 bytes 逐 byte 比對，
# 不符就拒絕開機（畫面空白卡住）。HLE 用同一組資料做驗證。
NINTENDO_LOGO = bytes.fromhex(
    "24FFAE51699AA2213D84820A84E409AD11248B98C0817F21A352BE199309CE20"
    "10464A4AF82731EC58C7E83382E3CEBF85F4DF94CE4B09C194568AC01372A7FC"
    "9F844D73A3CA9A615897A327FC039876231DC7610304AE56BF38840040A70EFD"
    "FF52FE036F9530F197FBC08560D68025A963BE03014E38E2F9A234FFBB3E0344"
    "780090CB88113A9465C07C6387F03CAFD625E48B380AAC7221D4F807"
)


class BIOS:
    def __init__(self, bus):
        self.bus = bus

    def _verify_logo(self):
        """比對卡匣表頭 logo（004h..09Fh）與 BIOS 內建 Nintendo logo；
        兩邊對等才允許開機（真機 BIOS 的行為）。"""
        cart = self.bus.cartridge
        if hasattr(cart, "logo"):
            logo = bytes(cart.logo)
        else:                                   # 後備：直接讀 ROM 表頭
            logo = bytes(self.bus.read8(0x08000004 + i) for i in range(156))
        if logo != NINTENDO_LOGO:
            raise RuntimeError(
                "Nintendo logo 驗證失敗：卡匣表頭 004h..09Fh 與 BIOS 內建 logo 不符，\n"
                "真機 BIOS 會拒絕開機（畫面空白卡住）。\n"
                f"  卡匣表頭開頭: {logo[:12].hex(' ').upper()}\n"
                f"  BIOS logo 開頭: {NINTENDO_LOGO[:12].hex(' ').upper()}\n"
                "確定要強制開機請用 verify_logo=False。")

    def boot(self, cpu, verify_logo=True):
        """HLE 冷開機：先驗證卡匣表頭的 Nintendo logo，兩邊對等才跳過
        BIOS logo 開機畫面、直接建立「BIOS 跑完」的狀態（對照 mGBA 的
        no-BIOS boot 行為）。verify_logo=False 可強制跳過驗證。"""
        bus = self.bus
        if verify_logo:
            self._verify_logo()
        # ── CPU 狀態（真 BIOS 跳進遊戲前留下的）──
        cpu.regs.r[3] = 0xBAAE187F          # BIOS checksum（mGBA HLE 也這樣設，遊戲會驗證）
        cpu.regs.r[13] = 0x03007F00          # user/system 模式 sp
        cpu.regs.r[14] = 0x08000000          # lr
        cpu.regs.r[15] = 0x08000000          # pc = 遊戲入口
        cpu.regs.cpsr = 0x1F                 # system 模式、中斷關閉
        # 分組堆疊：真 BIOS 會設定各模式的 sp（之後遊戲開中斷會用到）
        cpu.regs.banks[0x12] = [0x03007FA0, 0, 0]   # IRQ 模式 sp
        cpu.regs.banks[0x13] = [0x03007FE0, 0, 0]   # SVC 模式 sp
        cpu.regs.banks[0x1F] = [0x03007F00, 0, 0]   # SYS/USR 模式 sp
        # ── 顯示：BIOS 離開時螢幕是強制空白（遊戲自己會重設 DISPCNT）──
        bus.io[0x000:0x002] = b'\x80\x00'    # DISPCNT = 0x0080（forced blank）
        # ── 中斷：全部關閉 ──
        bus.io[0x200:0x202] = b'\x00\x00'    # IE = 0
        bus.io[0x202:0x204] = b'\x00\x00'    # IF = 0
        bus.io[0x208:0x20A] = b'\x00\x00'    # IME = 0
        bus.io[0x300] = 0x01                 # POSTFLG：BIOS 開機後 = 01h（GBATEK）

    def _div(self, cpu, num, den):
        """SWI 06h/07h 有號除法（GBATEK）：r0=商、r1=餘（正負同被除數）、r3=|商|。
        真機除以 0 會卡在無限迴圈；HLE 回傳保護值，不讓模擬卡死。"""
        q, r = _sdiv(num, den)
        cpu.regs.r[0] = q & 0xFFFFFFFF
        cpu.regs.r[1] = r & 0xFFFFFFFF
        cpu.regs.r[3] = abs(q) & 0xFFFFFFFF

    def call(self, cpu, num):
        if num == 0x01:                      # RegisterRamReset（GBATEK + 真 BIOS 實測）
            bus = self.bus
            flags = cpu.regs.r[0]
            if flags & 0x01:                 # 清 EWRAM（256K）
                bus.ewram[:] = bytes(len(bus.ewram))
            if flags & 0x02:                 # 清 IWRAM（保留最後 200h bytes）
                bus.iwram[:0x7E00] = bytes(0x7E00)
            if flags & 0x04:                 # 清 Palette（1K）
                bus.palette[:] = bytes(len(bus.palette))
            if flags & 0x08:                 # 清 VRAM（96K）
                bus.vram[:] = bytes(len(bus.vram))
            if flags & 0x10:                 # 清 OAM（1K）
                bus.oam[:] = bytes(len(bus.oam))
            if flags & 0x20:                 # SIO → 一般模式（SIO/RCNT 暫存器歸零）
                for a in range(0x120, 0x134):
                    bus.io[a] = 0
            if flags & 0x40:                 # 音效暫存器歸零
                for a in range(0x60, 0xA9):
                    bus.io[a] = 0
            if flags & 0x80:                 # 其他 IO 歸零（顯示/計時/DMA/中斷/按鍵…）
                for a in range(0x000, 0x060):
                    bus.io[a] = 0
                for a in range(0x0A9, 0x120):
                    bus.io[a] = 0
                for a in range(0x200, 0x20A):
                    bus.io[a] = 0
                bus.timers.reload = [0, 0, 0, 0]     # 內部狀態同步歸零
                bus.timers.counter = [0, 0, 0, 0]
                bus.timers.control = [0, 0, 0, 0]
                bus.timers.pres = [0, 0, 0, 0]
                bus.timers.cascade = [False] * 4
                bus.dma.cnt = [0, 0, 0, 0]
                bus.dma.sad = [0, 0, 0, 0]
                bus.dma.dad = [0, 0, 0, 0]
            # 真 BIOS 一定切到 forced blank（DISPCNT=0080h，畫面變白）
            bus.io[0x000] = 0x80
            bus.io[0x001] = 0x00
            return
        elif num == 0x02:                      # Halt：等待任意中斷（GBATEK：GBA = SWI 02h）
            # 實測真 BIOS：只寫 HALTCNT=0 進 Halt；不動 IME（喚醒只看 IE&IF）
            cpu.bus.io[0x301] = 0x00
            cpu.halted = True
            cpu.wait_irq = 0
            return
        elif num in (0x06, 0x07):              # Div / DivArm：有號除法（GBATEK）
            if num == 0x06:                    # Div：r0=被除數、r1=除數
                num_v, den = cpu.regs.r[0], cpu.regs.r[1]
            else:                              # DivArm：r0=除數、r1=被除數（交換）
                num_v, den = cpu.regs.r[1], cpu.regs.r[0]
            self._div(cpu, _signed32(num_v), _signed32(den))
            return
        elif num == 0x00:                      # SoftReset（GBATEK 16 章）：不返回呼叫者
            bus = self.bus
            # 依 [03007FFAh] 旗標決定重入點：0=ROM(08000000h)、非 0=RAM(02000000h)
            target = 0x08000000 if bus.iwram[0x7FFA] == 0 else 0x02000000
            for a in range(0x7E00, 0x8000):    # 清 200h bytes（含 BIOS IRQ 旗標/堆疊區）
                bus.iwram[a] = 0
            cpu.regs.banks[0x12] = [0x03007FA0, 0, 0]
            cpu.regs.banks[0x13] = [0x03007FE0, 0, 0]
            cpu.regs.banks[0x1F] = [0x03007F00, 0, 0]
            for i in range(13):                # R0-R12 = 0
                cpu.regs.r[i] = 0
            # 借 cpu.swi() 收尾跳目標（SYS 模式）；LR_svc/SPSR 已重設
            cpu.regs.banks[0x13][2] = 0x1F
            cpu.regs.r[14] = target
            return
        elif num == 0x08:                      # Sqrt：r0 = 整數平方根（已對照真 BIOS 實測）
            cpu.regs.r[0] = math.isqrt(cpu.regs.r[0] & 0xFFFFFFFF) & 0xFFFF
            return
        elif num == 0x09:                      # ArcTan：真 BIOS 多項式精確移植
            cpu.regs.r[0] = _biostan(cpu.regs.r[0])
            return
        elif num == 0x0A:                      # ArcTan2：真 BIOS 象限演算法精確移植
            cpu.regs.r[0] = _biosatan2(cpu.regs.r[0], cpu.regs.r[1])
            return
        elif num == 0x0D:                      # GetBiosChecksum（實測 = BAAE187Fh）
            cpu.regs.r[0] = 0xBAAE187F
            return
        elif num == 0x0E:                      # BgAffineSet（公式已對照真 BIOS 實測值）
            bus = self.bus
            src, dst, count = cpu.regs.r[0], cpu.regs.r[1], cpu.regs.r[2]
            for i in range(count):
                s = src + i * 20
                x0 = _signed32(bus.read32(s))
                y0 = _signed32(bus.read32(s + 4))
                dx = _s16(bus.read16(s + 8))
                dy = _s16(bus.read16(s + 10))
                sx = _s16(bus.read16(s + 12))
                sy = _s16(bus.read16(s + 14))
                a8 = (bus.read16(s + 16) >> 8) & 0xFF
                sin = _SINTAB[a8]
                cos = _SINTAB[(a8 + 64) & 0xFF]
                pa = _q8(cos * sx)
                pb = _q8(-sin * sx)
                pc = _q8(sin * sy)
                pd = _q8(cos * sy)
                d = dst + i * 16
                bus.write16(d + 0, pa & 0xFFFF)
                bus.write16(d + 2, pb & 0xFFFF)
                bus.write16(d + 4, pc & 0xFFFF)
                bus.write16(d + 6, pd & 0xFFFF)
                bus.write32(d + 8, (x0 - pa * dx - pb * dy) & 0xFFFFFFFF)
                bus.write32(d + 12, (y0 - pc * dx - pd * dy) & 0xFFFFFFFF)
            return
        elif num == 0x0F:                      # ObjAffineSet（參數公式與 BgAffineSet 相同）
            bus = self.bus
            src, dst = cpu.regs.r[0], cpu.regs.r[1]
            count, off = cpu.regs.r[2], cpu.regs.r[3]
            for i in range(count):
                s = src + i * 6
                sx = _s16(bus.read16(s))
                sy = _s16(bus.read16(s + 2))
                a8 = (bus.read16(s + 4) >> 8) & 0xFF
                sin = _SINTAB[a8]
                cos = _SINTAB[(a8 + 64) & 0xFF]
                # GBATEK：四個參數「每隔 off bytes」放一個（off=8 → 對應 OAM 結構）
                d = dst + i * off * 4
                bus.write16(d + 0 * off, _q8(cos * sx) & 0xFFFF)
                bus.write16(d + 1 * off, _q8(-sin * sx) & 0xFFFF)
                bus.write16(d + 2 * off, _q8(sin * sy) & 0xFFFF)
                bus.write16(d + 3 * off, _q8(cos * sy) & 0xFFFF)
            return
        elif num == 0x10:                      # BitUnPack（位元寬度擴展）
            bus = self.bus
            src, dst, info = cpu.regs.r[0], cpu.regs.r[1], cpu.regs.r[2]
            length = bus.read16(info)          # 來源長度（bytes）
            src_w = bus.read8(info + 2)        # 來源單位位寬（1/2/4/8）
            dst_w = bus.read8(info + 3)        # 目的單位位寬（1/2/4/8/16/32）
            raw_off = bus.read32(info + 4)
            zero_flag = (raw_off >> 31) & 1    # 1 = 零單位也加 offset
            off = raw_off & 0x7FFFFFFF
            # 來源位元：逐 byte、由 LSB 起取（實測真 BIOS 行為）
            units = []
            per_byte = 8 // max(src_w, 1)
            mask = (1 << src_w) - 1
            for i in range(length):
                b = bus.read8(src + i)
                for k in range(per_byte):
                    units.append((b >> (k * src_w)) & mask)
            # 目的單位：非 0 → +offset；0 → 依 zero_flag；由 LSB 起打包
            word = 0
            bitpos = 0
            words = []
            dmask = (1 << dst_w) - 1
            for u in units:
                v = (u + off) if (u or zero_flag) else 0
                word |= (v & dmask) << bitpos
                bitpos += dst_w
                if bitpos >= 32:
                    words.append(word & 0xFFFFFFFF)
                    word, bitpos = 0, 0
            if bitpos:
                words.append(word & 0xFFFFFFFF)
            for i, w in enumerate(words):
                bus.write32(dst + i * 4, w)
            return
        elif num in (0x11, 0x12):              # LZ77UnComp（Wram/Vram）
            bus = self.bus
            s, dst = cpu.regs.r[0], cpu.regs.r[1]
            length = bus.read32(s) >> 8
            s += 4
            out = bytearray()
            while len(out) < length:
                flags = bus.read8(s)
                s += 1
                for _ in range(8):
                    if len(out) >= length:
                        break
                    if flags & 0x80:
                        b0 = bus.read8(s)
                        b1 = bus.read8(s + 1)
                        s += 2
                        n = (b0 >> 4) + 3
                        disp = ((b0 & 0x0F) << 8) | b1
                        for _ in range(n):
                            out.append(out[len(out) - disp - 1])
                    else:
                        out.append(bus.read8(s))
                        s += 1
                    flags = (flags << 1) & 0xFF
            _flush16(bus, dst, out)
            return
        elif num == 0x13:                      # HuffUnComp（真 BIOS 0x1014 精確移植）
            bus = self.bus
            s, dst = cpu.regs.r[0], cpu.regs.r[1]
            header = bus.read32(s)
            size = header & 0xF                 # 資料單位位元（4/8）
            length = header >> 8                # 解壓後長度（bytes）
            tree_sz = bus.read8(s + 4)
            tree = s + 5                        # 根節點
            bits = s + 4 + (tree_sz + 1) * 2    # 位元流（Bit31 = 第一個位元）
            per_word = 32 // max(size, 1)
            words = (length + 3) // 4           # 真 BIOS：輸出一律 ceil(len/4) 個 word
            bitpos = 0

            def next_bit():
                nonlocal bitpos
                w = bus.read32(bits + (bitpos >> 5) * 4)
                b = (w >> (31 - (bitpos & 31))) & 1
                bitpos += 1
                return b

            ptr = tree
            node = bus.read8(ptr)
            for _ in range(words):
                word = 0
                for _ in range(per_word):
                    b = next_bit()
                    is_data = (node >> (7 - b)) & 1      # bit7=node0 是資料、bit6=node1
                    child = (ptr & ~1) + (node & 0x3F) * 2 + 2 + b
                    node = bus.read8(child)
                    if is_data:
                        word = ((word >> size) | (node << (32 - size))) & 0xFFFFFFFF
                        ptr = tree
                        node = bus.read8(ptr)
                    else:
                        ptr = child
                bus.write32(dst, word)
                dst += 4
            return
        elif num in (0x14, 0x15):              # RLUnComp（Wram/Vram）
            bus = self.bus
            s, dst = cpu.regs.r[0], cpu.regs.r[1]
            length = bus.read32(s) >> 8
            s += 4
            out = bytearray()
            while len(out) < length:
                flag = bus.read8(s)
                s += 1
                if flag & 0x80:                # 壓縮：同一 byte 重複 N 次
                    n = (flag & 0x7F) + 3
                    out += bytes([bus.read8(s)]) * n
                    s += 1
                else:                          # 未壓縮：N bytes 直接複製
                    n = (flag & 0x7F) + 1
                    out.extend(bus.read8(s + k) for k in range(n))
                    s += n
            _flush16(bus, dst, out)
            return
        elif num in (0x16, 0x17):              # Diff8bitUnFilter（Wram/Vram）
            bus = self.bus
            s, dst = cpu.regs.r[0], cpu.regs.r[1]
            length = bus.read32(s) >> 8
            s += 4
            out = bytearray()
            acc = 0
            for i in range(length):
                acc = (acc + bus.read8(s + i)) & 0xFF
                out.append(acc)
            _flush16(bus, dst, out)
            return
        elif num == 0x18:                      # Diff16bitUnFilter
            bus = self.bus
            s, dst = cpu.regs.r[0], cpu.regs.r[1]
            length = bus.read32(s) >> 8
            s += 4
            acc = 0
            for i in range(length // 2):
                acc = (acc + bus.read16(s + i * 2)) & 0xFFFF
                bus.write16(dst + i * 2, acc)
            return
        elif num == 0x19:                      # SoundBias：調 SOUNDBIAS 位準（保留高位）
            old = self.bus.read16(0x04000088)
            level = 0x000 if cpu.regs.r[0] == 0 else 0x200
            self.bus.write16(0x04000088, (old & ~0x3FF) | level)
            return
        elif num == 0x1F:                      # MidiKey2Freq（真 BIOS 0x18D8 精確移植）
            wa = cpu.regs.r[0]
            mk = cpu.regs.r[1] & 0xFF
            fp = cpu.regs.r[2] & 0xFF
            r2 = fp << 24
            if mk > 0xB2:                      # 超過 MIDI 178 音：夾住 + 用最大分數
                r2 = 0xFF000000
                mk = 0xB2
            v0 = _midi_val(mk)
            v1 = _midi_val(mk + 1)
            t = (((v1 - v0) & 0xFFFFFFFF) * r2) >> 32   # 半音內插（無號 64-bit 取高位）
            v = (t + v0) & 0xFFFFFFFF
            freq = self.bus.read32(wa + 4)              # WaveData.freq
            cpu.regs.r[0] = (freq * v) >> 32
            return
        elif num == 0x26:                      # HardReset：整機重開
            # 借收尾跳回 reset vector 0 → cpu.step 的暖開機 HLE 接手
            cpu.regs.banks[0x13][2] = 0x1F
            cpu.regs.r[14] = 0
            return
        elif num == 0x27:                      # CustomHalt：8bit 參數寫入 HALTCNT
            v = cpu.regs.r[2] & 0xFF
            cpu.bus.io[0x301] = v
            cpu.halted = True                  # 00h=Halt、80h=Stop（近似同 Halt）
            cpu.wait_irq = 0
            return
        elif num in (0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x25, 0x28, 0x29, 0x2A):
            # 音效驅動（1Ah-1Eh、28h-2Ah）與 MultiBoot（25h）：
            # 本模擬器無音效/對傳硬體，直接返回（遊戲流程可續行）
            return
        elif num == 0x03:                      # Stop：深眠模式（HLE 簡化：等同 NOP）
            # 真機只被 keypad/SIO/gamepak 中斷喚醒；先當 NOP
            return
        elif num == 0x0B:                      # CpuSet（GBATEK：4/2-byte 單位搬移）
            src   = cpu.regs.r[0]
            dst   = cpu.regs.r[1]
            ctrl  = cpu.regs.r[2]
            count = ctrl & 0x1FFFFF
            fill  = (ctrl >> 24) & 1

            # 來源/目的觸及 BIOS 區（0x0000-0x3FFF）→ 靜默拒絕（GBATEK）
            n_total = count * (4 if (ctrl >> 26) & 1 else 2)
            if (src < 0x4000 and src + n_total > 0) or \
               (dst < 0x4000 and dst + n_total > 0):
                return

            if (ctrl >> 26) & 1:               # 32-bit 模式（word）
                n = count * 4
                if fill:
                    v = cpu.bus.read32(src)    # 同一筆重複填
                    for i in range(0, n, 4):
                        cpu.bus.write32(dst + i, v)
                else:
                    for i in range(0, n, 4):
                        cpu.bus.write32(dst + i, cpu.bus.read32(src + i))
            else:                              # 16-bit 模式（halfword）
                n = count * 2
                if fill:
                    v = cpu.bus.read16(src)
                    for i in range(0, n, 2):
                        cpu.bus.write16(dst + i, v)
                else:
                    for i in range(0, n, 2):
                        cpu.bus.write16(dst + i, cpu.bus.read16(src + i))
            # 執行時間（GBATEK）：32bit 每 word 10 週期、16bit 每 2 半字 10 週期 + 19 開銷
            cost = 19 + count * (10 if (ctrl >> 26) & 1 else 5)
            cpu.bus._stall(cost)
            return
        elif num == 0x0C:                      # CpuFastSet（GBATEK：32-byte 區塊搬移）
            src   = cpu.regs.r[0]
            dst   = cpu.regs.r[1]
            ctrl  = cpu.regs.r[2]
            count = ctrl & 0x1FFFFF
            if count == 0:
                count = 0x100000               # 硬體規定：0 = 最大量
            count = (count + 7) & ~7           # GBA：無條件向上取整到 8 words（GBATEK）
            fill  = (ctrl >> 24) & 1

            # 來源/目的觸及 BIOS 區（0x0000-0x3FFF）→ 靜默拒絕（GBATEK）
            n_total = count * 4
            if (src < 0x4000 and src + n_total > 0) or \
               (dst < 0x4000 and dst + n_total > 0):
                return

            if fill:
                v = cpu.bus.read32(src)        # 同一 word 重複填
                for i in range(count):
                    cpu.bus.write32(dst + i * 4, v)
            else:
                for i in range(count):
                    cpu.bus.write32(dst + i * 4, cpu.bus.read32(src + i * 4))
            # 執行時間（GBATEK）：每 word 6 週期 + 19 開銷
            cost = 19 + count * 6
            cpu.bus._stall(cost)
            return
        elif num in (0x04, 0x05):              # IntrWait / VBlankIntrWait
            if num == 0x05:
                cpu.regs.r[0] = 1              # VBlankIntrWait = IntrWait(1, 1)
                cpu.regs.r[1] = 1
            flags = cpu.regs.r[1] & 0x3FFF
            cpu.bus.io[0x208] |= 1             # 強制 IME=1
            old = (cpu.bus.io[0x202] | (cpu.bus.io[0x203] << 8)) & flags
            if cpu.regs.r[0] == 0 and old:
                pass                           # 舊旗標已設 → 立即返回
            else:
                if cpu.regs.r[0] == 1:         # 丟棄舊旗標（BIOS RAM 副本）
                    cpu.bus.iwram[0x7FF8] &= ~(flags & 0xFF)
                    cpu.bus.iwram[0x7FF9] &= ~((flags >> 8) & 0xFF)
                cpu.halted = True
                cpu.wait_irq = flags
            return
        # 未知 SWI：真機 BIOS 對未知號碼只做「回傳」——等同 NOP
        # （這款遊戲的 NOP 沙漠會故意用偽 SWI 當跳板，不能當錯誤！）
        warned = getattr(self, "_warned", set())
        if num not in warned:
            warned.add(num)
            log.info("未知 SWI 0x%X → 當 NOP 跳過（真機 BIOS 也這樣）", num)
            self._warned = warned
        return