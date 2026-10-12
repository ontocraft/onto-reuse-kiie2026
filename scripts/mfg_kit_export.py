"""키트 그래프를 Neo4j 가 읽는 CSV(노드 · 관계)로 내보낸다. 데이터베이스에 접속하지 않는다.

    python scripts/mfg_kit_export.py                 # out/kit-neo4j/
    python scripts/mfg_kit_export.py --data 내자료 --qif a.qif

Neo4j 에서 읽는 법(로컬 인스턴스 · 빈 DB):

    neo4j-admin database import full --nodes=nodes.csv --relationships=rels.csv neo4j

⚠️ **운영 Neo4j 에 넣지 않는다.** 라벨에 `Kit` 접두어를 붙여 운영 라벨과 겹치지 않게 한다
   (프로젝트 규약 ②). 제약과 인덱스는 만들지 않는다.

RDF → LPG 변환 규칙: 개체는 노드, `rdf:type` 은 라벨(IRI 의 마지막 조각에 `Kit` 접두),
리터럴 속성은 노드 속성, 개체 사이 관계는 관계(이름은 IRI 의 마지막 조각). 시각 값 표현처럼
빈 노드로 매단 값은 `startsAt` · `endsAt` 속성으로 접는다.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from rdflib import BNode, Literal, URIRef

sys.path.insert(0, str(Path(__file__).parent))
import mfg_kit as kit  # noqa: E402


NAMES = {"BFO_0000057": "hasParticipant", "BFO_0000132": "occurrentPartOf", "BFO_0000015": "Process",
         "BFO_0000050": "partOf"}


def tail(iri) -> str:
    s = str(iri).rsplit("#", 1)[-1].rsplit("/", 1)[-1]
    return NAMES.get(s, s)


def rel_name(iri) -> str:
    """hasOutput → HAS_OUTPUT. Neo4j 관례대로 대문자 스네이크."""
    import re
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", tail(iri)).upper()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("kit/examples"))
    ap.add_argument("--qif", type=Path, nargs="*", default=kit.QIF_FILES)
    ap.add_argument("--out", type=Path, default=Path("out/kit-neo4j"))
    a = ap.parse_args()
    g, rules, closure = kit.build(a.data, a.qif)
    kit.materialize(g, rules, closure)

    # 시각 값 표현(빈 노드)은 속성으로 접는다
    folded = {}
    for s, p, o in g.triples((None, None, None)):
        if isinstance(o, BNode) and p in (kit.KIT.startsAt, kit.KIT.endsAt):
            v = g.value(o, kit.IOF.hasDateTimeInstantValue)
            if v is not None:
                folded[(s, p)] = str(v)
    skip = {o for (s, p), _ in folded.items() for o in g.objects(s, p) if isinstance(o, BNode)}

    labels: dict[URIRef, set] = defaultdict(set)
    props: dict[URIRef, dict] = defaultdict(dict)
    rels = []
    for s, p, o in g:
        if isinstance(s, BNode) or o in skip:
            continue
        if p == kit.RDF.type:
            labels[s].add("Kit" + tail(o))
        elif isinstance(o, Literal):
            props[s][tail(p)] = str(o)
        elif isinstance(o, URIRef):
            labels.setdefault(o, set())
            rels.append((s, rel_name(p), o))
    for (s, p), v in folded.items():
        props[s][tail(p)] = v

    a.out.mkdir(parents=True, exist_ok=True)
    keys = sorted({k for d in props.values() for k in d})
    with open(a.out / "nodes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([":ID", ":LABEL", *keys])
        for n in sorted(labels, key=str):
            w.writerow([str(n), ";".join(sorted(labels[n]) or ["KitNode"]),
                        *[props[n].get(k, "") for k in keys]])
    with open(a.out / "rels.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([":START_ID", ":TYPE", ":END_ID"])
        w.writerows((str(s), t, str(o)) for s, t, o in rels)
    kinds = defaultdict(int)
    for n in labels:
        for l in labels[n]:
            kinds[l] += 1
    print(f"노드 {len(labels)} · 관계 {len(rels)} · 라벨 {dict(sorted(kinds.items()))} → {a.out}")
    print("⚠️ 운영 Neo4j 에 넣지 않는다. 라벨은 모두 Kit 접두어다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
