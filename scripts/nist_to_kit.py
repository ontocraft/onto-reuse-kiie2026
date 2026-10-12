"""NIST SMS Test Bed 의 박스 조립체 자료를 시작 키트의 입력 형식으로 바꾼다.

    python scripts/nist_to_kit.py          # data/ontology/ext/nist-smstb/kit/ 에 쓴다
    python scripts/mfg_kit.py --data data/ontology/ext/nist-smstb/kit \\
        --qif "data/ontology/ext/nist-smstb/FAIR/7_28_2017 8_16_42 AM Box_Results.qif" \\
              data/ontology/ext/nist-smstb/QIF-IncomingInspection/BoxResults_19_samples.QIF

**왜 만들었나.** 시작 키트를 지어낸 MES·CMMS 가 아니라 실제 공개 자료로 시험한다
(2026-10-12). NIST 는 실제 CNC 가공 로그와 같은 부품의 QIF 검사 결과를 함께 공개했다.

자료 (https://github.com/usnistgov/smstestbed 커밋 968279f 의 `tdp/mtc/`, NIST 오픈 라이선스.
데이터 DOI 10.18434/T4/1503154):

| 받은 것 | 무엇 | 키트에서 |
|---|---|---|
| `PartData/Box-Hurco02-NNof20.txt` | 부품 하나를 가공한 동안의 MTConnect 기록 | 공정 실행(MES 대신) |
| `FAIR/… Box_Results.qif` | 초도품 검사(QIF 2.1). 일련번호 `2` ~ `20` | 측정 |
| `QIF-IncomingInspection/BoxResults_19_samples.QIF` | 수입검사(QIF 2.1). 일련번호 `BOXRESULTS_ANN_…` | 측정 |

**지어내는 값은 없다.** 공정 실행의 시작·끝은 로그의 첫·끝 시각이고, 설비는 파일 이름의
`Hurco02` 다. 정비 기록은 이 자료에 **없다**. 정비 상태 파일은 만들지 않는다.

⚠️ **가정 하나.** 같은 번호 NN 이면 같은 부품이라고 본다. 로그는 `NNof20`, 초도품 검사는
   `NN`, 수입검사는 `ANN` 이다. NIST 문서는 부품 인스턴스별로 정리했다고만 하고 이 대응
   규칙을 밝히지 않는다. 부품 대장의 `system` 열에 「가정」을 적어 둔다.
"""
from __future__ import annotations

import csv
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

D = Path("data/ontology/ext/nist-smstb")
OUT = D / "kit"
MACHINE = re.compile(r"^Box-(?P<machine>[A-Za-z]+\d+)-(?P<nn>\d+)of20$")


def local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def qif_serials(path: Path) -> tuple[str, list[str]]:
    root = ET.parse(path).getroot()
    model = next((e.text.strip() for e in root.iter() if local(e.tag) == "ModelNumber" and e.text),
                 path.stem)
    sns = [c.text.strip() for e in root.iter() if local(e.tag) == "ActualComponent"
           for c in e if local(c.tag) == "SerialNumber" and c.text]
    return model, sns


def number(serial: str) -> int | None:
    m = re.fullmatch(r"(\d+)", serial) or re.match(r"BOXRESULTS_A(\d+)_", serial)
    return int(m.group(1)) if m else None


def main() -> int:
    logs = sorted((D / "PartData").glob("Box-*of20.txt"))
    if not logs:
        sys.exit(f"{D}/PartData 가 없다. 머리말의 저장소에서 받는다")
    OUT.mkdir(parents=True, exist_ok=True)

    runs, machines = [], set()
    for p in logs:
        m = MACHINE.match(p.stem)
        if not m:
            continue
        rows = [line.rstrip("\n").split("|") for line in open(p, encoding="utf-8", errors="replace")
                if line.count("|") >= 2]
        times = [r[0] for r in rows if r[0][:2] == "20"]
        programs = sorted({r[2] for r in rows if r[1] == "Program_Name_Running" and r[2]})
        nn = int(m.group("nn"))
        machines.add(m.group("machine"))
        runs.append({"model_number": "BOX", "serial_number": str(nn), "run_id": p.stem,
                     "operation": "+".join(programs) or "unknown", "machine_id": m.group("machine"),
                     "operator_id": "", "start": times[0][:16], "end": times[-1][:16]})

    with open(OUT / "mes_process_runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(runs[0]))
        w.writeheader()
        w.writerows(runs)
    with open(OUT / "equipment_registry.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["equipment_id", "identifier", "system", "kind", "roles"])
        for mc in sorted(machines):
            w.writerow([mc.lower(), mc, "MTConnect", "CNC 머시닝센터", "equipment;maintainable"])

    # 부품 대장: 같은 번호 NN 의 이름 셋이 부품 하나를 지칭한다 (가정)
    registry = [(f"box-{int(r['serial_number']):02d}", f"BOX/{r['serial_number']}",
                 "MTConnect 로그 파일 번호") for r in runs]
    seen = {}
    for qif in sorted(D.rglob("*")):
        if qif.suffix.lower() != ".qif":
            continue
        model, sns = qif_serials(qif)
        joined = 0
        for sn in sns:
            nn = number(sn)
            if nn is None:
                continue
            registry.append((f"box-{nn:02d}", f"{model}/{sn}", f"{qif.parent.name} 일련번호 (가정: 같은 번호)"))
            joined += 1
        seen[qif.parent.name] = (len(sns), joined)
    with open(OUT / "part_registry.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["part_id", "identifier", "system"])
        w.writerows(registry)
    stale = OUT / "maintenance_states.csv"
    if stale.exists():
        stale.unlink()

    print(f"공정 실행 {len(runs)} (기계 {sorted(machines)}) · "
          f"시각 {min(r['start'] for r in runs)} ~ {max(r['end'] for r in runs)}")
    for k, (n, j) in seen.items():
        print(f"{k}: 일련번호 {n} · 번호로 부품에 맞춘 것 {j}")
    print(f"부품 대장 {len(registry)} 줄 → {OUT}")
    print("⚠️ 같은 번호면 같은 부품이라는 대응은 NIST 문서가 밝히지 않은 가정이다. 정비 기록은 없다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
