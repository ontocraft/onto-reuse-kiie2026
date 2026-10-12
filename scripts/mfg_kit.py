"""제조 AI 시작 키트. QIF 측정 파일과 CSV 셋을 넣으면 IOF 어휘로 그래프를 만들고 질문에 답한다.

    python scripts/mfg_kit.py                       # kit/examples 로 실행
    python scripts/mfg_kit.py --data 내자료디렉터리   # 같은 이름의 CSV 셋

넣는 것 (틀은 kit/templates/):

| 파일 | 어디서 오나 | 무엇을 잇나 |
|---|---|---|
| QIF 측정 파일 | CMM 소프트웨어 | 측정 → 판정 → 실물 부품(품번/일련번호) |
| mes_process_runs.csv | MES | 부품 → 공정 실행 → 설비 문자열 · 작업자 · 시각 |
| equipment_registry.csv | 설비 대장 | 시스템마다 다른 설비 문자열 → 설비 하나 · 역할 |
| maintenance_states.csv | CMMS | 설비 문자열 → 정비 상태 · 시작·끝 시각 · 작업지시 |

끊긴 곳 넷을 결정기록대로 메운다.

- 0035 측정은 품번/일련번호를 거쳐 공정에 잇는다 (QIF 의 ManufacturingProcessId 는 쓰지 않는다)
- 0036 설비 문자열은 IOF `Identifier` + `designates` 로 잇는다
- 0037 역할 분류는 적재할 때 구체화한다. 규칙은 IOF 배포판의 동치 정의에서 뽑는다
- 0038 정비 상태는 시간 구간으로 두고 「공정 시각이 구간 안에 드는가」로 묻는다

⚠️ kit/examples 의 MES·설비 대장·CMMS 는 **지어낸 시험 데이터**다. QIF 는 공개 표본이다.
   답의 개수에는 의미가 없다. 키트가 끝까지 잇는지를 보이는 것이다.
⚠️ 운영 Neo4j 에 닿지 않는다. rdflib 메모리 그래프만 쓴다.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

from rdflib import OWL, RDF, RDFS, BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import XSD

IOF = Namespace("https://spec.industrialontologies.org/ontology/construct/")
BFO = Namespace("http://purl.obolibrary.org/obo/")
QIF = Namespace("https://ontocraft.com/onto-reuse/qif#")
KIT = Namespace("https://ontocraft.com/onto-reuse/kit#")
EX = Namespace("https://ontocraft.com/onto-reuse/data/")
HAS_PARTICIPANT = BFO.BFO_0000057          # has participant at some time

IOF_SRC = Path("data/ontology/iof-src")
BFO_OWL = Path("data/ontology/ext/bfo-2020.owl")
QIF_FILES = [Path("data/ontology/ext/표본454.qif"), Path("data/ontology/ext/표본473.qif")]
ROLE = {"equipment": IOF.EquipmentRole, "maintainable": IOF.MaintainableMaterialItemRole}
STATE = {"Operating": IOF.OperatingState, "Degraded": IOF.DegradedState, "Failed": IOF.FailedState}
PREFIX = {"iof": IOF, "bfo": BFO, "qif": QIF, "kit": KIT}


def local(tag: str) -> str:
    return tag.split("}", 1)[-1]


# ───────────────────────────── IOF 에서 역할 규칙 뽑기 (0037)

def load_ontology() -> Graph:
    onto = Graph()
    onto.parse(BFO_OWL, format="xml")
    for name in ("core__Core.rdf", "maintenance__Maintenance.rdf"):
        onto.parse(IOF_SRC / name, format="xml")
    return onto


def role_rules(onto: Graph) -> tuple[list[tuple[URIRef, set, URIRef]], int]:
    """C ≡ (S1 ∨ S2 …) ∧ ∃hasRole.R 꼴의 동치 정의를 (C, {S…}, R) 로 뽑는다."""
    rules, skipped = [], 0
    for c, eq in onto.subject_objects(OWL.equivalentClass):
        if not isinstance(c, URIRef):
            continue
        parts = onto.value(eq, OWL.intersectionOf)
        if parts is None:
            continue
        supers, role = set(), None
        for p in Collection(onto, parts):
            if (p, RDF.type, OWL.Restriction) in onto and onto.value(p, OWL.onProperty) == IOF.hasRole:
                role = onto.value(p, OWL.someValuesFrom)
            elif isinstance(p, URIRef):
                supers.add(p)
            elif onto.value(p, OWL.unionOf) is not None:
                supers |= {u for u in Collection(onto, onto.value(p, OWL.unionOf)) if isinstance(u, URIRef)}
        if role is not None and isinstance(role, URIRef) and supers:
            rules.append((c, supers, role))
        elif role is not None:
            skipped += 1
    return rules, skipped


def superclasses(onto: Graph) -> dict[URIRef, set]:
    up = defaultdict(set)
    for s, o in onto.subject_objects(RDFS.subClassOf):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            up[s].add(o)
    closure: dict[URIRef, set] = {}

    def walk(c, seen):
        for p in up.get(c, ()):
            if p not in seen:
                seen.add(p)
                walk(p, seen)
        return seen
    for c in list(up):
        closure[c] = walk(c, set())
    return closure


def materialize(g: Graph, rules, closure) -> int:
    added = 0
    for x, r in list(g.subject_objects(IOF.hasRole)):
        rtypes = set(g.objects(r, RDF.type))
        xtypes = set(g.objects(x, RDF.type))
        xall = xtypes | {s for t in xtypes for s in closure.get(t, ())}
        for c, supers, role in rules:
            if role in rtypes and xall & supers and (x, RDF.type, c) not in g:
                g.add((x, RDF.type, c))
                added += 1
    return added


# ───────────────────────────── 적재

def when(g: Graph, subject, prop, text: str) -> None:
    """시각을 IOF 의 TemporalInstantValueExpression 으로 붙인다 (0038)."""
    if not text:
        return
    v = BNode()
    g.add((v, RDF.type, IOF.TemporalInstantValueExpression))
    g.add((v, IOF.hasDateTimeInstantValue, Literal(text + (":00" if len(text) == 16 else ""),
                                                   datatype=XSD.dateTime)))
    g.add((subject, prop, v))


def identifier(g: Graph, system: str, value: str, target) -> URIRef:
    """식별자 개체가 대상을 지칭한다 (0036). designates 는 함수적이다."""
    i = EX[f"id/{system}/{value}"]
    g.add((i, RDF.type, IOF.Identifier))
    g.add((i, KIT.identifierValue, Literal(value)))
    g.add((i, KIT.identifierSystem, Literal(system)))
    g.add((i, IOF.designates, target))
    return i


def load_qif(g: Graph, path: Path) -> dict:
    root = ET.parse(path).getroot()
    by_id = {e.get("id"): e for e in root.iter() if e.get("id")}
    parent = {c: p for p in root.iter() for c in p}
    model = next((c.text.strip() for e in root.iter() if local(e.tag) == "Part"
                  for c in e if local(c.tag) == "ModelNumber" and c.text), path.stem)
    parts = {}
    for e in root.iter():
        if local(e.tag) == "ActualComponent":
            sn = next((c.text.strip() for c in e if local(c.tag) == "SerialNumber" and c.text), None)
            if sn:
                part = EX[f"part/{model}/{sn}"]
                g.add((part, RDF.type, IOF.MaterialArtifact))
                identifier(g, "serial", f"{model}/{sn}", part)
                parts[e.get("id")] = part
    n = linked = 0
    for e in root.iter():
        if not local(e.tag).endswith("CharacteristicMeasurement"):
            continue
        n += 1
        m = EX[f"meas/{path.stem}/{e.get('id')}"]
        g.add((m, RDF.type, QIF.CharacteristicMeasurement))
        st = e.find("./{*}Status/{*}CharacteristicStatusEnum")
        if st is not None:
            g.add((m, QIF.status, Literal(st.text)))
        refs = [c.text.strip() for c in e if local(c.tag) == "ActualComponentId" and c.text]
        x = e
        while not refs and x in parent:          # 측정 묶음 단위로 부품을 가리키는 경우
            x = parent[x]
            if local(x.tag) == "MeasurementResults":
                refs = [i.text.strip() for c in x if local(c.tag) == "ActualComponentIds"
                        for i in c if i.text]
        for r in refs:
            if r in parts:
                g.add((m, QIF.ActualComponentId, parts[r]))
                linked += 1
    return {"model": model, "measurements": n, "linked": linked, "parts": len(parts)}


def load_registry(g: Graph, path: Path) -> dict[str, URIRef]:
    ids = {}
    for row in csv.DictReader(open(path, encoding="utf-8")):
        eq = EX[f"equipment/{row['equipment_id']}"]
        g.add((eq, RDF.type, IOF.MaterialArtifact))
        g.add((eq, RDFS.label, Literal(row["kind"])))
        for name in filter(None, row["roles"].split(";")):
            r = EX[f"equipment/{row['equipment_id']}/{name}"]
            g.add((r, RDF.type, ROLE[name]))
            g.add((eq, IOF.hasRole, r))
        identifier(g, row["system"], row["identifier"], eq)
        ids[row["identifier"]] = eq
    return ids


def designated(g: Graph, value: str):
    for i in g.subjects(KIT.identifierValue, Literal(value)):
        t = g.value(i, IOF.designates)
        if t is not None:
            return t
    return None


def load_mes(g: Graph, path: Path) -> dict:
    stats = Counter()
    for row in csv.DictReader(open(path, encoding="utf-8")):
        run = EX[f"run/{row['run_id']}"]
        g.add((run, RDF.type, IOF.ManufacturingProcess))
        g.add((run, RDFS.label, Literal(row["operation"])))
        when(g, run, KIT.startsAt, row["start"])
        when(g, run, KIT.endsAt, row["end"])
        part = designated(g, f"{row['model_number']}/{row['serial_number']}")
        if part is None:                           # QIF 에 없는 부품도 MES 에는 있을 수 있다
            part = EX[f"part/{row['model_number']}/{row['serial_number']}"]
            g.add((part, RDF.type, IOF.MaterialArtifact))
            identifier(g, "serial", f"{row['model_number']}/{row['serial_number']}", part)
            stats["QIF 에 없는 부품"] += 1
        g.add((run, IOF.hasOutput, part))
        eq = designated(g, row["machine_id"])
        if eq is None:
            stats["설비 대장에 없는 설비 문자열"] += 1
        else:
            g.add((run, HAS_PARTICIPANT, eq))
        if row.get("operator_id"):
            person = EX[f"person/{row['operator_id']}"]
            g.add((person, RDF.type, IOF.Person))
            identifier(g, "operator", row["operator_id"], person)
            g.add((run, HAS_PARTICIPANT, person))
        stats["공정 실행"] += 1
    return dict(stats)


def load_maintenance(g: Graph, path: Path) -> dict:
    stats = Counter()
    for k, row in enumerate(csv.DictReader(open(path, encoding="utf-8"))):
        eq = designated(g, row["identifier"])
        if eq is None:
            stats["설비 대장에 없는 설비 문자열"] += 1
            continue
        s = EX[f"state/{k}"]
        g.add((s, RDF.type, STATE[row["state"]]))
        g.add((eq, IOF.hasMaintenanceState, s))
        when(g, s, KIT.startsAt, row["start"])
        when(g, s, KIT.endsAt, row["end"])
        if row.get("work_order"):
            wo = EX[f"workorder/{row['work_order']}"]
            g.add((wo, RDF.type, IOF.MaintenanceWorkOrderRecord))
            g.add((wo, IOF.isAbout, s))
        stats["정비 상태"] += 1
    return dict(stats)


# ───────────────────────────── 질문

X1 = """
SELECT DISTINCT ?m ?part ?run ?eq ?stype WHERE {
  ?m a qif:CharacteristicMeasurement ; qif:status "FAIL" ; qif:ActualComponentId ?part .
  ?run a iof:ManufacturingProcess ; iof:hasOutput ?part ;
       kit:startsAt/iof:hasDateTimeInstantValue ?t ; bfo:BFO_0000057 ?eq .
  ?eq a iof:MaintainableMaterialItem ; iof:hasMaintenanceState ?s .
  ?s a ?stype ; kit:startsAt/iof:hasDateTimeInstantValue ?s0 .
  OPTIONAL { ?s kit:endsAt/iof:hasDateTimeInstantValue ?s1 }
  FILTER (?stype IN (iof:OperatingState, iof:DegradedState, iof:FailedState))
  FILTER (?t >= ?s0 && (!BOUND(?s1) || ?t < ?s1))
}"""

X1_STEPS = [
    ("부적합 측정", '?m a qif:CharacteristicMeasurement ; qif:status "FAIL" .'),
    ("→ 부품(품번/일련번호)", '?m qif:status "FAIL" ; qif:ActualComponentId ?p .'),
    ("→ 공정 실행", '?m qif:status "FAIL" ; qif:ActualComponentId ?p . ?r iof:hasOutput ?p .'),
    # 설비까지는 클래스 이름에 기대지 않는다. 역할을 가진 물질 인공물이면 설비에 닿은 것이다
    ("→ 설비", '?m qif:status "FAIL" ; qif:ActualComponentId ?p . ?r iof:hasOutput ?p ; '
              'bfo:BFO_0000057 ?e . ?e a iof:MaterialArtifact ; iof:hasRole ?ro .'),
    ("→ 정비 대상(클래스 이름)", '?m qif:status "FAIL" ; qif:ActualComponentId ?p . ?r iof:hasOutput ?p ; '
                           'bfo:BFO_0000057 ?e . ?e a iof:MaintainableMaterialItem .'),
]

P2 = """
SELECT ?run ?eq ?who WHERE {
  ?run a iof:ManufacturingProcess ; bfo:BFO_0000057 ?eq , ?who .
  ?eq a iof:PieceOfEquipment . ?who a iof:Person .
}"""

# X2: 정비 상태별로 그 구간에 만든 부품의 부적합 측정 비율
X2 = """
SELECT ?stype (COUNT(DISTINCT ?part) AS ?parts) (COUNT(DISTINCT ?fail) AS ?fails)
       (COUNT(DISTINCT ?m) AS ?meas) WHERE {
  ?run iof:hasOutput ?part ; kit:startsAt/iof:hasDateTimeInstantValue ?t ; bfo:BFO_0000057 ?eq .
  ?eq iof:hasMaintenanceState ?s . ?s a ?stype ; kit:startsAt/iof:hasDateTimeInstantValue ?s0 .
  OPTIONAL { ?s kit:endsAt/iof:hasDateTimeInstantValue ?s1 }
  FILTER (?stype IN (iof:OperatingState, iof:DegradedState, iof:FailedState))
  FILTER (?t >= ?s0 && (!BOUND(?s1) || ?t < ?s1))
  ?m qif:ActualComponentId ?part .
  OPTIONAL { ?m qif:status "FAIL" . BIND(?m AS ?fail) }
} GROUP BY ?stype"""


def count(g: Graph, pattern: str) -> int:
    q = f"SELECT (COUNT(DISTINCT ?m) AS ?n) WHERE {{ {pattern} }}"
    return int(next(iter(g.query(q, initNs=PREFIX)))[0])


def vocabulary(g: Graph) -> Counter:
    """그래프가 쓴 클래스와 속성을 출처별로 센다. 키트가 새로 만든 것이 몇인가."""
    terms = set(g.predicates()) | set(g.objects(None, RDF.type))
    c = Counter()
    for t in terms:
        s = str(t)
        c["IOF" if s.startswith(str(IOF)) else "BFO" if s.startswith(str(BFO)) else
          "QIF 요소 이름" if s.startswith(str(QIF)) else "키트" if s.startswith(str(KIT)) else
          "RDF/RDFS"] += 1
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("kit/examples"))
    ap.add_argument("--qif", type=Path, nargs="*", default=QIF_FILES)
    a = ap.parse_args()
    t0 = time.time()

    onto = load_ontology()
    rules, skipped = role_rules(onto)
    closure = superclasses(onto)
    print(f"IOF 에서 뽑은 역할 규칙 {len(rules)} 개 (다른 꼴이라 건너뜀 {skipped})")

    g = Graph()
    for q in a.qif:
        s = load_qif(g, q)
        print(f"QIF {q.name}: 품번 {s['model']} · 측정 {s['measurements']} · 부품 {s['parts']} · "
              f"측정→부품 {s['linked']}")
    load_registry(g, a.data / "equipment_registry.csv")
    print("MES:", load_mes(g, a.data / "mes_process_runs.csv"))
    print("CMMS:", load_maintenance(g, a.data / "maintenance_states.csv"))

    before = len(list(g.query(X1, initNs=PREFIX)))
    steps_before = [count(g, pattern) for _, pattern in X1_STEPS]
    added = materialize(g, rules, closure)
    after = list(g.query(X1, initNs=PREFIX))
    print(f"\n역할 분류 구체화로 더한 타입 {added} 개")
    print(f"X1 답: 구체화 전 {before} 건 → 후 {len(after)} 건")
    print(f"  {'':24s} 분류 전  분류 후")
    for (label, pattern), b in zip(X1_STEPS, steps_before):
        print(f"  {label:24s} {b:6d}  {count(g, pattern):6d}")
    by_state = Counter(str(r.stype).rsplit("/", 1)[-1] for r in after)
    print(f"  → 그때의 정비 상태   {len(after):5d}   {dict(by_state)}")

    p2 = list(g.query(P2, initNs=PREFIX))
    print(f"\nP2 공정 실행의 설비와 작업자: {len({r.run for r in p2})} 건의 공정 실행에서 답함")
    print("X2 정비 상태별 부적합 (시험 데이터라 비율에 의미 없음)")
    for r in g.query(X2, initNs=PREFIX):
        print(f"  {str(r.stype).rsplit('/', 1)[-1]:16s} 부품 {r.parts} · 측정 {r.meas} · FAIL {r.fails}")

    v = vocabulary(g)
    print(f"\n그래프가 쓴 어휘: {dict(v)}")
    print(f"키트가 새로 만든 것: {sorted(str(t).rsplit('#', 1)[-1] for t in set(g.predicates()) if str(t).startswith(str(KIT)))}")
    print(f"트리플 {len(g)} · 걸린 시간 {time.time() - t0:.1f}s")
    print("\n⚠️ kit/examples 의 MES·설비 대장·CMMS 는 지어낸 시험 데이터다. QIF 는 공개 표본이다.")
    return 0 if after else 1


if __name__ == "__main__":
    sys.exit(main())
