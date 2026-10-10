"""역량 질문 X1 을 실제로 질의해 어디서 끊기는지 본다.

    .venv/bin/python scripts/연구/mfg_x1_run.py

X1: 「부적합이 발생했을 때 그 부품을 만든 공정과 그 공정에 쓰인 설비의 정비 상태를
확인한다」. `mfg_cover.py` 는 X1 의 요구 요소가 스키마에 **있다**고만 기록한다.
이 스크립트는 인스턴스를 넣고 SPARQL 로 **답이 나오는지** 본다.

**왜 만들었나.** 학회 원고가 「답을 받아 본 질문은 0 개」라고 적었다. 2026-10-10 에
X1 하나라도 실행해 「어디서 끊기는가」를 결과로 보이기로 했다.

세 단계로 넣는다. **단계마다 무엇이 실제 자료이고 무엇이 시험 데이터인지 가른다.**

- A. 실제 자료만: 공개 QIF 측정 파일 두 개의 측정 기록을 그대로 옮긴다
- B. 시험 데이터 1: A 에 공정 실행 기록을 지어 넣는다. 설비는 QIF 처럼 문자열로만 둔다
- C. 시험 데이터 2: B 에 설비 개체와 정비 상태, 그리고 본 연구가 더한
     「설비를 가리킨다」를 넣는다

⚠️ B 와 C 의 공정·설비·정비 상태는 **지어낸 것**이다. 현장 자료가 아니다.
   이 단계들은 질의가 어느 연결에서 끊기는지를 보이려는 것이며, 답의 개수에는
   의미가 없다. 원고에 B·C 의 개수를 성과처럼 적지 않는다.

⚠️ 운영 Neo4j 에 닿지 않는다. rdflib 의 메모리 그래프만 쓴다.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from rdflib import RDF, RDFS, Graph, Literal, Namespace

EXT = Path("data/ontology/ext")
SAMPLES = ["표본454.qif", "표본473.qif"]
NS = "{http://qifstandards.org/xsd/qif3}"

# QIF 요소 이름을 그대로 쓴 우리 변환이다. QIF 가 RDF 를 내지 않으므로 이름공간은 우리가 정한다
QIF = Namespace("https://ontocraft.com/onto-reuse/qif#")
IOF = Namespace("https://spec.industrialontologies.org/ontology/construct/")
EX = Namespace("https://ontocraft.com/onto-reuse/x1#")

# X1 전체. 측정 → 공정 실행 기록 → 설비(물질 인공물 + 정비 대상 역할) → 정비 상태
X1 = """
SELECT ?m ?proc ?equip ?state WHERE {
  ?m a qif:CharacteristicMeasurement ; qif:status "FAIL" ;
     qif:ManufacturingProcessId ?proc .
  ?proc a qif:ManufacturingProcessTraceability ;
        ex:refersToEquipment ?equip .
  ?equip a iof:MaterialArtifact ; iof:hasRole ?r .
  ?r a iof:MaintainableMaterialItemRole .
  ?equip iof:hasMaintenanceState ?state .
}"""

# 같은 질문을 역할 정의 클래스 이름으로 물은 것. 추론기 없이는 답이 없어야 한다
X1_BY_CLASS = """
SELECT ?m ?equip WHERE {
  ?m a qif:CharacteristicMeasurement ; qif:status "FAIL" ;
     qif:ManufacturingProcessId/ex:refersToEquipment ?equip .
  ?equip a iof:MaintainableMaterialItem ; iof:hasMaintenanceState ?state .
}"""

# 연결마다 몇 건이 살아남는가
STEPS = [
    ("부적합 측정", '?m a qif:CharacteristicMeasurement ; qif:status "FAIL" .'),
    ("→ 공정 실행 기록", '?m a qif:CharacteristicMeasurement ; qif:status "FAIL" ; '
                     'qif:ManufacturingProcessId ?p . ?p a qif:ManufacturingProcessTraceability .'),
    ("→ 설비 개체", '?m a qif:CharacteristicMeasurement ; qif:status "FAIL" ; '
                 'qif:ManufacturingProcessId ?p . ?p ex:refersToEquipment ?e . '
                 '?e a iof:MaterialArtifact .'),
    ("→ 정비 상태", '?m a qif:CharacteristicMeasurement ; qif:status "FAIL" ; '
                 'qif:ManufacturingProcessId ?p . ?p ex:refersToEquipment ?e . '
                 '?e iof:hasRole ?r . ?r a iof:MaintainableMaterialItemRole . '
                 '?e iof:hasMaintenanceState ?s .'),
]
PREFIX = {"qif": QIF, "iof": IOF, "ex": EX}


def load_samples(g: Graph) -> dict[str, tuple[int, int, int]]:
    """측정 기록을 옮긴다. 판정은 그 측정 요소의 **직속** Status 만 본다.

    하위 요소에도 Status 가 있어서 문서 전체를 훑으면 판정 수가 부풀려진다.
    """
    seen = {}
    for name in SAMPLES:
        root = ET.parse(EXT / name).getroot()
        n = fail = with_pid = 0
        for e in root.iter():
            if not e.tag.replace(NS, "").endswith("CharacteristicMeasurement"):
                continue
            n += 1
            m = EX[f"{name}/m{e.get('id')}"]
            g.add((m, RDF.type, QIF.CharacteristicMeasurement))
            st = e.find(f"{NS}Status/{NS}CharacteristicStatusEnum")
            if st is not None:
                g.add((m, QIF.status, Literal(st.text)))
                fail += st.text == "FAIL"
            pid = e.find(f"{NS}ManufacturingProcessId")
            if pid is not None:
                with_pid += 1
                g.add((m, QIF.ManufacturingProcessId, EX[f"{name}/p{pid.text}"]))
        seen[name] = (n, fail, with_pid)
    return seen


def add_process_records(g: Graph) -> int:
    """시험 데이터. 부적합 측정마다 공정 실행 기록을 잇는다. 설비는 문자열로만 둔다."""
    fails = sorted(g.subjects(QIF.status, Literal("FAIL")))
    for i, m in enumerate(fails):
        p = EX[f"test/process{i % 3 + 1}"]
        g.add((m, QIF.ManufacturingProcessId, p))
        g.add((p, RDF.type, QIF.ManufacturingProcessTraceability))
        g.add((p, QIF.MachineIdentifier, Literal(f"M-0{i % 3 + 1}")))
    return len(fails)


def add_equipment(g: Graph) -> None:
    """시험 데이터. 설비 개체·역할·정비 상태와 「설비를 가리킨다」를 넣는다.

    「설비를 가리킨다」는 QIF 의 MachineIdentifier 문자열을 설비 개체의 식별자와
    맞춰 잇는다. 이 맞춤이 본 연구가 더한 연결이다.
    """
    equipment = {}
    for k in (1, 2, 3):
        e = EX[f"test/machine{k}"]
        g.add((e, RDF.type, IOF.MaterialArtifact))
        g.add((e, RDFS.label, Literal(f"M-0{k}")))
        for role in (IOF.EquipmentRole, IOF.MaintainableMaterialItemRole):
            r = EX[f"test/machine{k}/{role.split('/')[-1]}"]
            g.add((r, RDF.type, role))
            g.add((e, IOF.hasRole, r))
        s = EX[f"test/machine{k}/state"]
        g.add((s, RDF.type, IOF.MaintenanceState))
        g.add((e, IOF.hasMaintenanceState, s))
        equipment[f"M-0{k}"] = e
    for p, _, code in list(g.triples((None, QIF.MachineIdentifier, None))):
        if str(code) in equipment:
            g.add((p, EX.refersToEquipment, equipment[str(code)]))


def report(g: Graph, title: str) -> int:
    counts = []
    for label, pattern in STEPS:
        q = f"SELECT (COUNT(DISTINCT ?m) AS ?n) WHERE {{ {pattern} }}"
        counts.append((label, int(next(iter(g.query(q, initNs=PREFIX)))[0])))
    answers = len(list(g.query(X1, initNs=PREFIX)))
    by_class = len(list(g.query(X1_BY_CLASS, initNs=PREFIX)))
    print(f"\n{title}")
    for label, n in counts:
        print(f"  {label:14s} {n:5d}")
    cut = next((label for label, n in counts if n == 0), None)
    print(f"  X1 답 {answers} 건" + (f" · 끊긴 곳: {cut}" if cut else ""))
    print(f"  같은 질문을 클래스 이름(MaintainableMaterialItem)으로 물으면 {by_class} 건")
    return answers


def main() -> int:
    if not all((EXT / s).is_file() for s in SAMPLES):
        sys.exit("표본이 없다. mfg_qif.py 머리말의 명령으로 받는다")
    g = Graph()
    seen = load_samples(g)
    for name, (n, fail, pid) in seen.items():
        print(f"{name}: 측정 {n} · 부적합 판정 {fail} · 공정 참조 {pid}")

    a = report(g, "A. 실제 자료만 (공개 QIF 측정 파일 두 개)")
    add_process_records(g)
    b = report(g, "B. + 공정 실행 기록 (시험 데이터, 설비는 문자열)")
    add_equipment(g)
    c = report(g, "C. + 설비 개체·정비 상태·「설비를 가리킨다」 (시험 데이터)")
    print("\n⚠️ B·C 의 공정·설비·정비 상태는 지어낸 시험 데이터다. 답의 개수에는 의미가 없다.")
    return 0 if a == 0 and b == 0 and c > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
