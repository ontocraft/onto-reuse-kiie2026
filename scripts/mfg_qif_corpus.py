"""공개 QIF 파일 전체에서 품질 쪽 역량 질문이 답을 얻는지 파일마다 센다.

    python scripts/mfg_qif_corpus.py            # 표
    python scripts/mfg_qif_corpus.py --files    # 파일별 판정

**왜 만들었나.** 학회 원고의 5 절과 7 절은 공개 측정 파일 두 개와 질문 하나(X1)에
기댔다. 2026-10-11 에 근거의 폭을 넓히기로 했다. QIF 관리 단체가 공개한 예제 파일
전체에서, QIF 가 맡는 질문 다섯의 **QIF 구간**이 답을 얻는지 본다.

| 질문 | QIF 구간이 답했다고 보는 조건 |
|---|---|
| Q1 공차와 적합 판정 | 판정이 있는 측정이 항목 → 명목 → 정의를 거쳐 공차를 가진 정의에 닿는다 |
| Q2 부적합의 이력 | 판정이 FAIL 인 측정에 측정 시각(TimeStamp)이 있다. 느슨한 기준(Q2*)은 FAIL 이 있고 보고서 작성일이라도 있다 |
| Q3 검사 계획 | 계획(Plan)이 잴 특성을 지정하고(MeasureEvaluateAll 또는 CharacteristicItemIds) 같은 파일의 특성 항목에 측정 장비(MeasurementDeviceIds)가 있다. 장비는 계획 안이 아니라 특성 항목에 붙는다(2026-10-11 확인). 특성만 지정한 것은 Q3* 로 센다 |
| P2 공정 실행의 설비와 작업자 | 공정 실행 기록에 설비 식별자나 작업자 식별자가 있다 |
| X1 부적합에서 공정으로 | FAIL 측정의 ManufacturingProcessId 가 설비 식별자를 가진 공정 실행 기록에 닿는다 |

⚠️ **QIF 구간만 본다.** X1 은 그 뒤에 설비와 정비 기록이 더 있어야 답한다.
   여기서 「답함」은 그 질문이 QIF 에 요구하는 부분이 채워졌다는 뜻이다.
⚠️ **예제 파일이다.** 표준의 기능을 보여 주려고 만든 파일이 많다. 현장 기록 관행을
   대표하지 않는다. 같은 예제의 변형(_w_UUIDs, form_only 등)은 따로 센다.

받는 곳 (커밋 고정):

    git clone https://github.com/QualityInformationFramework/qif-community /tmp/qc
    git -C /tmp/qc checkout -q 64268c175a3058d09db29c14869b94b781518709
    mkdir -p data/ontology/ext/qif-community && cp -R /tmp/qc/samples data/ontology/ext/qif-community/
    # qif-workshop 99f0993 의 models/*.qif 넷은 data/ontology/ext/qif-workshop/ 에 둔다
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

DIRS = [Path("data/ontology/ext/qif-community/samples"), Path("data/ontology/ext/qif-workshop")]
# 같은 예제의 변형: 식별자 형식만 다르거나(_w_UUIDs · _W_QPIDS) 형상만 뺀 것(form_only).
# 2026-10-13 검토에서 변형 쌍을 따로 세라는 지적을 받았다. 변형을 뺀 값도 함께 낸다
VARIANT = re.compile(r"(_w_UUIDs|_W_QPIDS|-?form_only)", re.I)
NS = "{http://qifstandards.org/xsd/qif3}"
QUESTIONS = ["Q1", "Q2", "Q2*", "Q3", "Q3*", "P2", "X1"]


def local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def child(e, name):
    for c in e:
        if local(c.tag) == name:
            return c
    return None


def judge(path: Path) -> dict:
    root = ET.parse(path).getroot()
    by_id: dict[str, ET.Element] = {}
    meas, items, plans, mpts = [], [], [], []
    for e in root.iter():
        if e.get("id"):
            by_id[e.get("id")] = e
        t = local(e.tag)
        if t.endswith("CharacteristicMeasurement"):
            meas.append(e)
        elif t == "Plan":
            plans.append(e)
        elif t == "ManufacturingProcessTraceability":
            mpts.append(e)

    def status(m):
        s = child(m, "Status")
        s = child(s, "CharacteristicStatusEnum") if s is not None else None
        return s.text if s is not None else None

    def ref(e, name):
        r = child(e, name)
        return by_id.get(r.text.strip()) if r is not None and r.text else None

    def has_tolerance(d):
        return d is not None and any("Tolerance" in local(c.tag) for c in d.iter())

    judged = [m for m in meas if status(m)]
    fails = [m for m in judged if status(m) == "FAIL"]

    q1 = 0
    for m in judged:
        item = ref(m, "CharacteristicItemId")
        nominal = ref(item, "CharacteristicNominalId") if item is not None else None
        definition = ref(nominal, "CharacteristicDefinitionId") if nominal is not None else None
        q1 += has_tolerance(definition)

    q2 = sum(child(m, "TimeStamp") is not None for m in fails)
    report_date = any(local(e.tag) in ("ReportPreparationDate", "InspectionStart") for e in root.iter())
    q2_loose = len(fails) if fails and report_date else 0
    # 계획이 잴 특성을 지정했는가, 장비까지 지정했는가
    plan_chars = sum(any(local(e.tag) in ("MeasureEvaluateAll", "CharacteristicItemIds")
                         for e in p.iter()) for p in plans)
    devices = any(local(e.tag) == "MeasurementDeviceIds" and len(e) for e in root.iter())
    q3 = plan_chars if devices else 0
    p2 = sum(child(t, "MachineIdentifier") is not None or child(t, "OperatorIdentifier") is not None
             for t in mpts)

    x1 = 0
    for m in fails:
        pid = child(m, "ManufacturingProcessId")
        if pid is None or not pid.text:
            continue
        target = by_id.get(pid.text.strip())
        # ManufacturingProcessId 는 공정 실행 기록 하나를 가리킨다
        if target is not None and local(target.tag) == "ManufacturingProcessTraceability" \
                and child(target, "MachineIdentifier") is not None:
            x1 += 1

    # 0035: 공정 참조 대신 실물 부품의 일련번호까지 가는가. 측정 묶음 단위 참조도 따라간다
    parent = {c: p for p in root.iter() for c in p}

    def components(m):
        ids = [c.text.strip() for c in m if local(c.tag) == "ActualComponentId" and c.text]
        x = m
        while not ids and x in parent:
            x = parent[x]
            if local(x.tag) == "MeasurementResults":
                ids = [i.text.strip() for c in x if local(c.tag) == "ActualComponentIds"
                       for i in c if i.text]
        return [by_id[i] for i in ids if i in by_id]
    to_part = to_serial = 0
    for m in fails:
        cs = components(m)
        to_part += bool(cs)
        to_serial += any((c.text or "").strip() for p_ in cs for c in p_
                         if local(c.tag) == "SerialNumber")

    return {"측정": len(meas), "판정": len(judged), "FAIL": len(fails),
            "FAIL→부품": to_part, "FAIL→일련번호": to_serial,
            "계획": len(plans), "공정기록": len(mpts),
            "Q1": q1, "Q2": q2, "Q2*": q2_loose, "Q3": q3, "Q3*": plan_chars, "P2": p2, "X1": x1,
            "공정참조": sum(child(m, "ManufacturingProcessId") is not None for m in meas)}


def main() -> int:
    files = sorted(p for d in DIRS if d.exists() for p in d.rglob("*") if p.suffix.lower() == ".qif")
    if not files:
        sys.exit("QIF 파일이 없다. 머리말의 명령으로 받는다")
    rows = {}
    for p in files:
        try:
            rows[p] = judge(p)
        except ET.ParseError as e:
            print(f"⚠️ 읽지 못함 {p.name}: {e}")
    n = len(rows)
    has_meas = [p for p, r in rows.items() if r["판정"]]
    has_fail = [p for p, r in rows.items() if r["FAIL"]]
    print(f"파일 {n} · 판정이 있는 측정을 담은 파일 {len(has_meas)} · FAIL 을 담은 파일 {len(has_fail)} · "
          f"계획을 담은 파일 {sum(1 for r in rows.values() if r['계획'])} · "
          f"공정 실행 기록을 담은 파일 {sum(1 for r in rows.values() if r['공정기록'])}")
    total = defaultdict(int)
    for r in rows.values():
        for k, v in r.items():
            total[k] += v
    print(f"측정 {total['측정']} · 판정 {total['판정']} · FAIL {total['FAIL']} · "
          f"측정의 공정 참조 {total['공정참조']} · 공정 실행 기록 {total['공정기록']}")
    print(f"FAIL {total['FAIL']} 중 부품까지 {total['FAIL→부품']} · 일련번호까지 {total['FAIL→일련번호']} "
          f"(파일 {sum(1 for r in rows.values() if r['FAIL→일련번호'])} 개)\n")
    print("질문  QIF 구간이 답한 파일 / 전체   (근거 요소 수)")
    for q in QUESTIONS:
        k = sum(1 for r in rows.values() if r[q])
        print(f"  {q:4s} {k:3d} / {n}   ({total[q]})")
    # 변형을 뺀 값과 두 공개 측정 파일의 몫
    base = {p: r for p, r in rows.items() if not VARIANT.search(p.name)}
    ws = sum(r["FAIL"] for p, r in rows.items() if "workshop" in str(p))
    print(f"\n변형 {n - len(base)} 개를 뺀 {len(base)} 개: 측정 {sum(r['측정'] for r in base.values())} · "
          f"FAIL {sum(r['FAIL'] for r in base.values())} · 일련번호까지 {sum(r['FAIL→일련번호'] for r in base.values())} · "
          + " · ".join(f"{q} {sum(1 for r in base.values() if r[q])}" for q in QUESTIONS if "*" not in q))
    print(f"qif-workshop 측정 파일 두 개의 FAIL {ws} / {total['FAIL']} ({100 * ws / total['FAIL']:.0f}%)")
    if "--files" in sys.argv:
        print()
        for p, r in rows.items():
            mark = " ".join(q if r[q] else "·" * len(q) for q in QUESTIONS)
            print(f"  {mark}   측정 {r['측정']:4d} FAIL {r['FAIL']:3d} 계획 {r['계획']} "
                  f"공정 {r['공정기록']}  {p.relative_to(p.parents[1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
