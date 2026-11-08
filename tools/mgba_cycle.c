/* mGBA per-instruction cycle dump for timing parity diagnostics.
 *
 * Build:
 *   gcc -O2 -I"%TEMP%\mgba_src\include" -I"%TEMP%\mgba_src\src" \
 *       -o mgba_cycle.exe mgba_cycle.c "%TEMP%\mgba_src\build\libmgba.a" \
 *       -lm -lshlwapi -lole32 -luuid -lshell32
 *
 * Usage: mgba_cycle.exe rom.gba [steps] [waitcnt_hex] [read_addr_hex]
 *
 *   read_addr_hex：跑完 steps 之後用 GBALoad32 讀該位址並印 `mem[...]`，
 *   用嚟對照測試 ROM 寫入 timer 讀數／記憶體的結果。
 */
#include <mgba/core/core.h>
#include <mgba/core/config.h>
#include <mgba/core/interface.h>
#include <mgba/internal/gba/gba.h>
#include <mgba/internal/gba/io.h>
#include <mgba/internal/gba/memory.h>
#include <mgba/internal/arm/arm.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char** argv) {
	if (argc < 2) {
		fprintf(stderr, "usage: %s rom.gba [steps] [waitcnt_hex]\n", argv[0]);
		return 1;
	}
	const char* rom = argv[1];
	int steps = argc > 2 ? atoi(argv[2]) : 20;
	uint32_t readAddr = argc > 4 ? (uint32_t) strtoul(argv[4], NULL, 16) : 0;
	uint16_t waitcnt = argc > 3 ? (uint16_t) strtoul(argv[3], NULL, 16) : 0x4010;

	unsigned width = 240, height = 160;
	color_t* buffer = calloc(width * height * 4, sizeof(color_t));
	struct mCore* core = mCoreFind(rom);
	if (!core) {
		fprintf(stderr, "mCoreFind failed\n");
		return 1;
	}
	core->init(core);
	core->setVideoBuffer(core, buffer, width);
	mCoreConfigInit(&core->config, "ref");
	mCoreConfigLoad(&core->config);
	struct mCoreOptions opts = { 0 };
	mCoreConfigMap(&core->config, &opts);
	opts.audioSync = false;
	opts.videoSync = false;
	mCoreConfigLoadDefaults(&core->config, &opts);
	mCoreLoadConfig(core);
	if (!mCoreLoadFile(core, rom)) {
		fprintf(stderr, "load failed\n");
		return 1;
	}
	core->reset(core);

	struct GBA* gba = core->board;
	gba->memory.io[REG_WAITCNT >> 1] = waitcnt;
	GBAAdjustWaitstates(gba, waitcnt);

	uint32_t last = gba->cpu->cycles;
	for (int index = 0; index < steps; ++index) {
		uint32_t pc = gba->cpu->gprs[ARM_PC];
		core->step(core);
		uint32_t now = gba->cpu->cycles;
		printf("%3d pc=%08x op=%08x delta=%2d total=%u pref=%d region=%d s16=%d n16=%d last=%08x\n", index, pc, gba->cpu->prefetch[0], (int) (now - last), now, gba->memory.prefetch, gba->memory.activeRegion, gba->cpu->memory.activeSeqCycles16, gba->cpu->memory.activeNonseqCycles16, gba->memory.lastPrefetchedPc);
		last = now;
	}
	if (readAddr) {
		uint32_t value = GBALoad32(gba->cpu, readAddr, 0);
		printf("mem[%08x]=%08x\n", readAddr, value);
	}
	core->deinit(core);
	free(buffer);
	return 0;
}
