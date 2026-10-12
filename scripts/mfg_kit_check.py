"""적재하기 전에 자료가 어디서 끊길지 점검한다. 원고 표 「키트를 쓰기 전에 확인할 것」의 기계 판정.

    python scripts/mfg_kit_check.py                          # kit/examples
    python scripts/mfg_kit_check.py --data 내자료 --qif a.qif

| 항목 | 무엇을 보나 | 걸리면 |
|---|---|---|
| 일련번호 표기 | MES 의 품번/일련번호가 QIF 나 measurements.csv 의 부품에 있는가. 부품 대장이 있으면 그것을 거친다 | 측정 → 공정이 끊긴다 |
| 일련번호 고유성 | 같은 일련번호가 다른 품번에도 있는가 | 품번 없이 이으면 섞인다 |
| 설비 문자열 | MES · CMMS · 기계 사건의 설비 문자열이 설비 대장에 있는가 | 공정 → 설비가 끊긴다 |
| 정비 상태 시각 | 시작 시각이 없거나, 한 설비에 끝 시각 없는 상태가 둘 이상이거나, 구간이 겹치는가 | 「그때」를 물을 수 없거나 둘이 나온다 |
| 정비 상태 파일 | 있는가 | X1 의 마지막 연결을 답할 수 없다 |

역할이 바뀌면 분류를 다시 적용하는 것은 자료로 판정할 수 없어 여기 없다.
끊기는 항목이 있으면 종료 코드 1 이다. 적재는 하지 않는다.
"""
from __future__ import annotations

import argparse
import csv
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mfg_kit as kit  # noqa: E402


def rows(path: Path) -> list[dict]:
    return list(csv.DictReader(open(path, encoding="utf-8"))) if path.exists() else []


def qif_parts(path: Path) -> set[str]:
    root = ET.parse(path).getroot()
    model = next((c.text.strip() for e in root.iter() if kit.local(e.tag) == "Part"
                  for c in e if kit.local(c.tag) == "ModelNumber" and c.text), path.stem)
    return {f"{model}/{c.text.strip()}" for e in root.iter() if kit.local(e.tag) == "ActualComponent"
            for c in e if kit.local(c.tag) == "SerialNumber" and c.text}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("kit/examples"))
    ap.add_argument("--qif", type=Path, nargs="*", default=kit.QIF_FILES)
    a = ap.parse_args()
    problems = 0

    # 부품 대장: 문자열 → 부품 ID
    alias = {r["identifier"]: r["part_id"] for r in rows(a.data / "part_registry.csv")}
    quality = set()
    for q in a.qif:
        quality |= qif_parts(q)
    quality |= {f"{r['model_number']}/{r['serial_number']}" for r in rows(a.data / "measurements.csv")}
    canon = lambda key: alias.get(key, key)  # noqa: E731
    quality_c = {canon(k) for k in quality}

    mes = rows(a.data / "mes_process_runs.csv")
    mes_keys = {f"{r['model_number']}/{r['serial_number']}" for r in mes}
    unmatched = sorted(k for k in mes_keys if canon(k) not in quality_c)
    print(f"[일련번호 표기] 품질 쪽 부품 {len(quality_c)} · MES 부품 {len(mes_keys)} · "
          f"MES 에만 있는 부품 {len(unmatched)}" + (f"  예: {unmatched[:3]}" if unmatched else ""))
    if unmatched and len(unmatched) == len(mes_keys):
        print("   ✗ MES 부품이 하나도 품질 쪽과 맞지 않는다. 표기가 다르거나 품번이 다르다")
        problems += 1

    # 같은 일련번호가 다른 품번에 있는가. 부품 대장이 같은 부품으로 묶은 것은 세지 않는다
    by_serial = defaultdict(set)
    for k in quality | mes_keys:
        _, _, serial = k.partition("/")
        by_serial[serial].add(canon(k))
    dup = {s: m for s, m in by_serial.items() if len(m) > 1}
    print(f"[일련번호 고유성] 서로 다른 품번에 같은 일련번호 {len(dup)} 개"
          + (f"  예: {list(dup.items())[:2]}  → 품번과 함께 써야 한다" if dup else ""))

    registry = {r["identifier"] for r in rows(a.data / "equipment_registry.csv")}
    used = Counter()
    for name, col in (("mes_process_runs.csv", "machine_id"), ("maintenance_states.csv", "identifier"),
                      ("machine_events.csv", "identifier")):
        for r in rows(a.data / name):
            if r.get(col) and r[col] not in registry:
                used[(name, r[col])] += 1
    print(f"[설비 문자열] 설비 대장 {len(registry)} 개 · 대장에 없는 문자열 {len(used)} 개"
          + (f"  예: {list(used)[:3]}" if used else ""))
    if used:
        print("   ✗ 그 문자열의 기록은 설비에 닿지 않는다")
        problems += 1

    states = rows(a.data / "maintenance_states.csv")
    if not states:
        print("[정비 상태 파일] 없다  ✗ X1 의 마지막 연결을 답할 수 없다")
        problems += 1
    else:
        no_start = [r for r in states if not r.get("start")]
        open_by_eq = Counter(r["identifier"] for r in states if not r.get("end"))
        many_open = {e: n for e, n in open_by_eq.items() if n > 1}
        overlap = 0
        by_eq = defaultdict(list)
        for r in states:
            if r.get("start"):
                by_eq[r["identifier"]].append((r["start"], r.get("end") or "9999"))
        for iv in by_eq.values():
            iv.sort()
            overlap += sum(1 for (s0, e0), (s1, _) in zip(iv, iv[1:]) if s1 < e0)
        print(f"[정비 상태 시각] 상태 {len(states)} · 시작 없음 {len(no_start)} · "
              f"끝 없는 상태가 둘 이상인 설비 {len(many_open)} · 겹치는 구간 {overlap}")
        if no_start or many_open or overlap:
            print("   ✗ 「그때」를 물을 수 없거나 답이 둘 나온다")
            problems += 1

    print(f"\n끊기는 항목 {problems} 개" + (" · 적재해도 된다" if not problems else ""))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
