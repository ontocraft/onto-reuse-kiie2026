"""키트가 자리를 잡은 뒤 질문 하나를 더하는 비용을 잰다.

    python scripts/mfg_kit_more.py

**왜 만들었나.** 원고는 「새 질문은 질의 하나로 더한다」고 적었다(P2 · X2). 그 말을
질문 셋으로 더 재서, 어휘를 더했는지와 질의 길이 · 실행 시간을 기록한다(2026-10-12).

| 질문 | 어디서 | 무엇을 묻나 |
|---|---|---|
| Q1 | 역량 질문 목록 | 이 특성의 측정값과 상·하한은 얼마이고 판정은 무엇인가 |
| Q2 | 역량 질문 목록 | 이 품번의 부적합이 처음 난 공정 실행은 언제이고 그 뒤로 몇 건인가 |
| M11 | 역량 질문 목록 | 이 설비는 지금 가동 상태인가 열화·고장 상태인가 (끝 시각이 없는 상태) |
| X5 | 새 질문 | 이 정비 작업지시가 다룬 상태 구간 동안 만든 부품은 몇 개이고 그중 부적합은 몇 건인가 |

⚠️ Q2 는 측정 시각이 아니라 **공정 실행 시각**으로 답한다. 공개 QIF 에 측정 시각이 없다
   (mfg_qif_corpus.py 의 Q2 = 0). 원래 질문의 뜻을 좁힌 것이다.
⚠️ 사람이 질의를 쓰는 데 걸린 시간은 재지 않았다. 잰 것은 질의 줄 수, 어휘 추가 여부,
   적재를 뺀 실행 시간이다.
⚠️ kit/examples 의 MES · CMMS 는 지어낸 시험 데이터다. 답의 값에는 뜻이 없다.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mfg_kit as kit  # noqa: E402

QUESTIONS = {
    "Q1 공차와 적합 판정": """
SELECT ?part ?char ?value ?status ?tol ?min ?max WHERE {
  ?m a qif:CharacteristicMeasurement ; qif:ActualComponentId ?part ; rdfs:label ?char ;
     qif:status ?status ; qif:Value ?value ; qif:CharacteristicDefinitionId ?d .
  OPTIONAL { ?d qif:ToleranceValue ?tol }
  OPTIONAL { ?d qif:MinValue ?min ; qif:MaxValue ?max }
}""",
    "Q2 부적합의 이력(공정 시각 기준)": """
SELECT ?model (MIN(?t) AS ?first) (COUNT(DISTINCT ?m) AS ?fails) WHERE {
  ?m qif:status "FAIL" ; qif:ActualComponentId ?part .
  ?run iof:hasOutput ?part ; kit:startsAt/iof:hasDateTimeInstantValue ?t .
  ?i iof:designates ?part ; kit:identifierSystem "serial" ; kit:identifierValue ?key .
  BIND (STRBEFORE(?key, "/") AS ?model)
} GROUP BY ?model""",
    "M11 설비의 현재 상태": """
SELECT ?eq ?stype WHERE {
  ?eq iof:hasMaintenanceState ?s . ?s a ?stype .
  FILTER (?stype IN (iof:OperatingState, iof:DegradedState, iof:FailedState))
  FILTER NOT EXISTS { ?s kit:endsAt ?end }
}""",
    "X5 작업지시 구간의 부품과 부적합": """
SELECT ?wo (COUNT(DISTINCT ?part) AS ?parts) (COUNT(DISTINCT ?fail) AS ?fails) WHERE {
  ?wo a iof:MaintenanceWorkOrderRecord ; iof:isAbout ?s .
  ?s kit:startsAt/iof:hasDateTimeInstantValue ?s0 .
  OPTIONAL { ?s kit:endsAt/iof:hasDateTimeInstantValue ?s1 }
  ?eq iof:hasMaintenanceState ?s .
  ?run bfo:BFO_0000057 ?eq ; iof:hasOutput ?part ; kit:startsAt/iof:hasDateTimeInstantValue ?t .
  FILTER (?t >= ?s0 && (!BOUND(?s1) || ?t < ?s1))
  OPTIONAL { ?m qif:ActualComponentId ?part ; qif:status "FAIL" . BIND(?m AS ?fail) }
} GROUP BY ?wo""",
}


def main() -> int:
    g, rules, closure = kit.build(Path("kit/examples"), kit.QIF_FILES)
    kit.materialize(g, rules, closure)
    vocab_before = {t for t in set(g.predicates()) | set(g.objects(None, kit.RDF.type))}
    print(f"\n{'질문':34s} 줄  답  실행(ms)")
    for name, q in QUESTIONS.items():
        lines = len([l for l in q.strip().splitlines() if l.strip()])
        t0 = time.perf_counter()
        rows = list(g.query(q, initNs=kit.PREFIX))
        ms = (time.perf_counter() - t0) * 1000
        print(f"{name:34s} {lines:2d}  {len(rows):2d}  {ms:7.1f}")
        for r in rows[:4]:
            print("    ", " · ".join(str(v).rsplit("/", 1)[-1] for v in r))
    # Q1 의 덤: 형상 공차(ToleranceValue 하나, 값이 그 이하면 적합)에서만 판정과 값을 대조한다.
    # 치수 공차는 명목값 기준 편차라 명목값까지 읽어야 하므로 여기서 대조하지 않는다
    rows = list(g.query(QUESTIONS["Q1 공차와 적합 판정"], initNs=kit.PREFIX))
    form = [r for r in rows if r.tol is not None and str(r.status) in ("PASS", "FAIL")]
    size = [r for r in rows if r.min is not None]
    inconsistent = [r for r in form if (str(r.status) == "FAIL") != (float(r.value) > float(r.tol))]
    print(f"\nQ1: 공차가 붙은 측정 {len(rows)} (형상 공차 {len(form)} · 치수 공차 {len(size)}) · "
          f"형상 공차에서 판정과 값이 다른 것 {len(inconsistent)}")
    for r in inconsistent[:5]:
        print(f"     {str(r.part).rsplit('/', 1)[-1]} {r.char} 값 {float(r.value):.4f} 공차 {float(r.tol):.4f} 판정 {r.status}")
    vocab_after = {t for t in set(g.predicates()) | set(g.objects(None, kit.RDF.type))}
    print(f"\n어휘 추가 {len(vocab_after - vocab_before)} 개 · 스키마 변경 없음")
    print("⚠️ 답의 값은 시험 데이터라 뜻이 없다. 잰 것은 줄 수 · 어휘 추가 · 실행 시간이다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
