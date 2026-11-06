def passed(cond, cpsr):
    n = (cpsr >> 31) & 1
    z = (cpsr >> 30) & 1
    c = (cpsr >> 29) & 1
    v = (cpsr >> 28) & 1
    if   cond == 0x0: return z == 1        # EQ
    elif cond == 0x1: return z == 0        # NE
    elif cond == 0x2: return c == 1        # CS
    elif cond == 0x3: return c == 0        # CC
    elif cond == 0x4: return n == 1        # MI
    elif cond == 0x5: return n == 0        # PL
    elif cond == 0x6: return v == 1        # VS
    elif cond == 0x7: return v == 0        # VC
    elif cond == 0x8: return c == 1 and z == 0  # HI
    elif cond == 0x9: return c == 0 or z == 1   # LS
    elif cond == 0xA: return n == v        # GE
    elif cond == 0xB: return n != v        # LT
    elif cond == 0xC: return z == 0 and n == v   # GT
    elif cond == 0xD: return z == 1 or n != v    # LE
    elif cond == 0xE: return True          # AL（無條件）
    elif cond == 0xF: return True          # SWI（不是條件碼，直接執行）
    else:
        raise NotImplementedError(f"cond 0x{cond:X} 還沒實作")