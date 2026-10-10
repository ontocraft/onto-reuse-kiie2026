"""역할 정의 클래스 넷이 정말 역할로 분류되는지 추론기(HermiT)로 돌려 본다.

    .venv/bin/python scripts/연구/mfg_hermit.py

**왜 만들었나.** 학회 원고 6.2 절은 「물질 인공물이 설비 역할을 가지면 정의상
설비에 속한다」고 적고 「추론기를 실행하지 않았다」로 막아 두었다. 2026-10-10 검토에서
그것을 실제로 돌려 보라는 의견을 받았다. 이 스크립트가 그 확인이다.

무엇을 넣나. 클래스마다 물질 인공물(`MaterialArtifact`) 개체 하나에 그 역할 개체를
`hasRole` 로 붙인다. 대조로 두 역할을 함께 가진 개체와 역할이 없는 개체를 넣는다.
**우리 스키마의 인스턴스가 아니라 정의를 시험하는 개체다.**

준비물. Java(`brew install openjdk`), owlready2(`.venv/bin/pip install owlready2`),
BFO 2020 OWL 을 `data/ontology/ext/bfo-2020.owl` 에 받는다:

    curl -sL -o data/ontology/ext/bfo-2020.owl http://purl.obolibrary.org/obo/bfo/2020/bfo.owl

⚠️ IOF 의 `owl:imports` 는 떼고 읽는다. 원격 import 를 따라가지 않으려는 것이다.
   떼는 것은 BFO(위에서 따로 읽는다)와 주석 어휘(`AnnotationVocabulary`)뿐이고,
   주석 어휘는 논리 공리를 담지 않는다.
"""
from __future__ import annotations

import re
import sys
import tempfile
import time
from pathlib import Path

import owlready2 as o

SRC = Path("data/ontology/iof-src")
BFO = Path("data/ontology/ext/bfo-2020.owl")
C = "https://spec.industrialontologies.org/ontology/construct/"
JAVA = Path("/opt/homebrew/opt/openjdk/bin/java")
# 원고 표 3 의 넷. `mfg_schema.py roles` 가 같은 넷을 낸다
TESTS = [("MaintainableMaterialItem", "MaintainableMaterialItemRole", "정비 대상"),
         ("PieceOfEquipment", "EquipmentRole", "설비"),
         ("MaterialComponent", "MaterialComponentRole", "부품"),
         ("RawMaterial", "RawMaterialRole", "재료")]


def main() -> int:
    if not BFO.is_file():
        sys.exit(f"{BFO} 가 없다. 머리말의 curl 로 받는다")
    if JAVA.is_file():
        o.JAVA_EXE = str(JAVA)
    w = o.World()
    w.get_ontology(BFO.resolve().as_uri()).load()
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("core__Core.rdf", "maintenance__Maintenance.rdf"):
            text = (SRC / name).read_text(encoding="utf-8")
            stripped = Path(tmp) / name
            stripped.write_text(re.sub(r"<owl:imports [^>]*/>", "", text), encoding="utf-8")
            w.get_ontology(stripped.as_uri()).load()

    for cls, _, label in TESTS:
        print(f"{label:6s} {cls:26s} ≡ {w[C + cls].equivalent_to}")

    MA = w[C + "MaterialArtifact"]
    t = w.get_ontology("http://example.org/hermit-test#")
    with t:
        x = {}
        for cls, role, _ in TESTS:
            x[cls] = MA("x_" + cls)
            x[cls].hasRole = [w[C + role]("r_" + role)]
        both = MA("pump_both")
        both.hasRole = [w[C + "EquipmentRole"]("r_eq"),
                        w[C + "MaintainableMaterialItemRole"]("r_mi")]
        bare = MA("pump_no_role")

    t0 = time.time()
    o.sync_reasoner_hermit(w, infer_property_values=False, debug=0)
    print(f"\nHermiT {time.time() - t0:.1f}s · 일관성 통과")

    def member(ind, cls):
        return w[C + cls] in ind.INDIRECT_is_a

    ok = 0
    for cls, _, label in TESTS:
        got = member(x[cls], cls)
        ok += got
        print(f"  물질 인공물 + {label} 역할 → {cls}: {got}")
    pe, mi = member(both, "PieceOfEquipment"), member(both, "MaintainableMaterialItem")
    print(f"  두 역할을 함께 가진 개체 → 설비 {pe} · 정비 대상 {mi}")
    pe0, mi0 = member(bare, "PieceOfEquipment"), member(bare, "MaintainableMaterialItem")
    print(f"  역할이 없는 개체 → 설비 {pe0} · 정비 대상 {mi0}")
    print(f"\n역할로 분류된 것 {ok} / {len(TESTS)}")
    return 0 if ok == len(TESTS) and pe and mi and not (pe0 or mi0) else 1


if __name__ == "__main__":
    sys.exit(main())
