"""Parse suite_probe Timing logs into per-test/per-config deltas."""
import re
import sys
from collections import Counter, defaultdict

LINE = re.compile(r"^(ARM|Thumb)/(ROM \.\.\.|ROM P\.\.|ROM \.N\.|ROM PN\.|ROM \.\.S|ROM P\.S|ROM \.NS|ROM PNS|WRAM|IWRAM): Got\s+(-?\d+) vs\s+(-?\d+): FAIL$")
TEST = re.compile(r"^Timing test: (.*)$")


def parse(path):
    rows = []
    test = None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        m = TEST.match(line)
        if m:
            test = m.group(1)
            continue
        m = LINE.match(line)
        if m and test:
            mode, config, got, expected = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
            rows.append((test, mode, config, got, expected, got - expected))
    return rows


def main(path):
    rows = parse(path)
    print(f"parsed {len(rows)} failures")
    deltas = Counter(r[5] for r in rows)
    print("delta histogram:", dict(sorted(deltas.items())))
    print()
    by_config = defaultdict(Counter)
    for r in rows:
        by_config[(r[0], r[1])][r[2]] += 1
    configs = ["ROM ...", "ROM P..", "ROM .N.", "ROM PN.", "ROM ..S", "ROM P.S", "ROM .NS", "ROM PNS", "WRAM", "IWRAM"]
    tests = []
    for r in rows:
        if r[0] not in tests:
            tests.append(r[0])
    for t in tests:
        cells = []
        for c in configs:
            n = by_config[(t, "ARM")].get(c, 0) + by_config[(t, "Thumb")].get(c, 0)
            cells.append(f"{n:2d}" if n else " .")
        print(f"{t[:44]:44s} " + " ".join(f"{c:>7s}" for c in ["...", "P..", ".N.", "PN.", "..S", "P.S", ".NS", "PNS", "WRAM", "IWRAM"]))
        print(f"{'':44s} " + " ".join(f"{x:>7s}" for x in cells))
        print()


if __name__ == "__main__":
    main(sys.argv[1])
