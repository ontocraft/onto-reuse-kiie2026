"""역량 질문 26 개가 키트에서 어디까지 와 있는지 센다. 배정과 실행을 가른다.

    python scripts/mfg_kit_status.py

| 상태 | 뜻 |
|---|---|
| 실행됨 | 키트 예제 자료로 질의를 써서 답을 받았다 (`mfg_kit.py` · `mfg_kit_more.py`) |
| 자료만 있으면 | 필요한 요소가 스키마에 다 있다(`mfg_cover.py` 배정). 예제 자료에 그 자료가 없어 아직 실행하지 않았다 |
| 스키마 보강 | 요소 일부가 없다(`mfg_cover.py` 부분 배정) |

⚠️ 「실행됨」 목록은 손으로 적는다. 질의를 실제로 쓴 질문만 넣는다. 배정 목록에 없는
   질문을 실행됨에 넣으면 멈춘다.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# 질의를 써서 답을 받은 질문. Q2 는 측정 시각이 없어 공정 실행 시각으로 좁혀 답했다
EXECUTED = {"X1": "mfg_kit.py", "P2": "mfg_kit.py", "X2": "mfg_kit.py",
            "Q1": "mfg_kit_more.py", "Q2": "mfg_kit_more.py (공정 시각으로 좁힘)",
            "M11": "mfg_kit_more.py"}


def main() -> int:
    spec = importlib.util.spec_from_file_location("cover", Path(__file__).parent / "mfg_cover.py")
    cover = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cover)
    status = {k.split()[0]: v[1] for k, v in cover.NEED.items()}
    bad = [q for q in EXECUTED if status.get(q) != "답함"]
    if bad:
        sys.exit(f"실행됨에 넣었지만 배정이 아닌 질문: {bad}")
    groups = {"실행됨": [], "자료만 있으면": [], "스키마 보강": []}
    for q, st in status.items():
        groups["실행됨" if q in EXECUTED else "자료만 있으면" if st == "답함" else "스키마 보강"].append(q)
    total = sum(len(v) for v in groups.values())
    for k, v in groups.items():
        print(f"{k:8s} {len(v):2d}  {' '.join(v)}")
    print(f"합계 {total}")
    return 0 if total == 26 else 1


if __name__ == "__main__":
    sys.exit(main())
