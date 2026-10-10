"""QIF 3.0 스키마에서 무엇이 정의되어 있는지 센다.

    .venv/bin/python scripts/연구/mfg_qif.py types      # 관심 타입의 필드
    .venv/bin/python scripts/연구/mfg_qif.py sample     # 표본이 그중 무엇을 채웠나
    .venv/bin/python scripts/연구/mfg_qif.py counts     # 파일별 complexType 수

**왜 만들었나.** 2026-09-30 에 루트 스키마(`QIFDocument.xsd`)만 갖고 「표준에 시각이
없다」 「공정으로 잇는 것을 우리가 만들어야 한다」고 적었다. 배포판을 받아 보니 둘 다
정의되어 있었다. 루트 스키마는 제약의 xpath 만 담고 타입 정의는 하위 라이브러리에 있다.
**이 스크립트가 그 착오를 되풀이하지 않게 한다.**

배포판을 받는다 (13MB · ANSI QIF 3.0 · 2018):

    curl -sL -o /tmp/QIF3.zip \\
      "https://qifstandards.org/wp-content/uploads/2014/08/QIF3.0-2018-ANSI.zip"
    unzip -q -o /tmp/QIF3.zip 'xsd/*' -d /tmp/qif3
    cp /tmp/qif3/xsd/QIFLibrary/*.xsd /tmp/qif3/xsd/QIFApplications/*.xsd \\
      data/ontology/ext/

⚠️ `data/` 는 저장소에 넣지 않는다. 표준 배포판이라 받으면 된다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

EXT = Path("data/ontology/ext")

# 역량 질문에 걸리는 타입만 본다. 전부 보면 144 개까지 나온다
# (파일, 타입 이름, 무엇인가, 표본에서 이 타입에 해당하는 요소의 태그 끝)
WANT = [
    ("Characteristics.xsd", "CharacteristicMeasurementBaseType", "측정값과 판정",
     "CharacteristicMeasurement"),
    ("Characteristics.xsd", "CharacteristicItemBaseType", "제품 구조의 자리",
     "CharacteristicItem"),
    ("Traceability.xsd", "ManufacturingProcessTraceabilityType", "공정 실행 기록",
     "ManufacturingProcessTraceability"),
    ("Traceability.xsd", "InspectionTraceabilityType", "검사 실행 기록",
     "InspectionTraceability"),
    ("QIFPlan.xsd", "PlanType", "검사 계획", "Plan"),
]

EL = re.compile(r'<xs:element\b([^>]*?)/?>')


def base_of(path: Path, tn: str) -> str | None:
    """이 타입이 무엇을 물려받는가. 직접 선언만 세고 있음을 밝히려고 함께 낸다."""
    if not path.exists():
        return None
    s = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(rf'<xs:complexType name="{tn}".*?\n  </xs:complexType>', s, re.S)
    if not m:
        return None
    b = re.search(r'<xs:extension base="([^"]+)"', m.group())
    return b.group(1) if b else None


def fields(path: Path, tn: str) -> list[tuple[str, str, str]] | None:
    if not path.exists():
        return None
    s = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(rf'<xs:complexType name="{tn}".*?\n  </xs:complexType>', s, re.S)
    if not m:
        return None
    out = []
    for e in EL.finditer(m.group()):
        a = e.group(1)
        nm = re.search(r'name="([^"]+)"', a)
        if not nm:
            continue
        ty = re.search(r'type="([^"]+)"', a)
        mn = re.search(r'minOccurs="([^"]+)"', a)
        out.append((nm.group(1), ty.group(1) if ty else "", mn.group(1) if mn else "1"))
    return out


def types() -> int:
    missing = 0
    for fn, tn, what, _ in WANT:
        r = fields(EXT / fn, tn)
        print(f"\n=== {tn}  ({what} · {fn}) ===")
        if r is None:
            print("  파일이나 타입이 없다. 머리말의 명령으로 배포판을 받는다")
            missing += 1
            continue
        for n, t, mn in r:
            mark = " " if mn == "0" else "*"
            print(f"  {mark} {n:30s} {t:30s} min={mn}")
        base = base_of(EXT / fn, tn)
        print(f"  (직접 선언 {len(r)} 개. * 는 필수"
              + (f" · 물려받는 것: {base}" if base else "") + ")")
    return 1 if missing else 0


def sample() -> int:
    """표본이 스키마의 어느 칸을 채웠나. 정의가 있다는 것과 자료가 있다는 것은 다르다.

    **집계 기준을 못 박는다.**

    - 「스키마 칸」은 그 `complexType` 의 `xs:sequence` 안에 **직접 선언된** 자식
      요소의 수다. `complexContent/extension` 으로 물려받은 것은 세지 않는다.
    - 「채운 칸」은 표본에서 **그 타입의 요소 가운데 하나 이상**이 그 자식을 가진
      경우다. **레코드별 채움률이 아니다.** 600 건 중 1 건만 채워도 채운 것으로 센다.
    - 선택 요소(`minOccurs="0"`)가 비어 있는 것은 **표준 위반이 아니다.** 표준이
      허용한다. 다만 우리 역량 질문에는 필수일 수 있고, 그 판정은 질문별로 따로 한다.
    """
    import xml.etree.ElementTree as ET
    qifs = sorted(EXT.glob("*.qif")) or sorted(Path("/tmp").glob("*.qif"))
    if not qifs:
        print("표본이 없다. qif-workshop 의 models/ 에서 받는다:")
        print("  curl -sL -o /tmp/s.qif https://raw.githubusercontent.com/"
              "QualityInformationFramework/qif-workshop/HEAD/models/000454_D-MV-FH-2.qif")
        return 1
    NS = "{http://qifstandards.org/xsd/qif3}"
    for q in qifs:
        root = ET.parse(q).getroot()
        print(f"\n=== {q.name} ===")
        for fn, tn, what, suffix in WANT:
            r = fields(EXT / fn, tn) or []
            if not r:
                continue
            # ⚠️ 그 타입의 요소 아래에서만 센다. 문서 전체에서 이름을 찾으면
            #    남의 자식까지 세어 값이 부풀려진다 (2026-09-30 에 그렇게 틀렸다)
            kids: set[str] = set()
            n_el = 0
            for e in root.iter():
                if e.tag.replace(NS, "").endswith(suffix):
                    n_el += 1
                    kids.update(c.tag.replace(NS, "") for c in e)
            got = [n for n, _, _ in r if n in kids]
            print(f"  {tn:38s} {len(got):2d} / {len(r):2d} 칸   요소 {n_el} 건")
            miss = [n for n, _, _ in r if n not in kids]
            if miss:
                print(f"      빈 칸: {' · '.join(miss)}")
    return 0


def counts() -> int:
    for f in sorted(EXT.glob("*.xsd")):
        n = len(re.findall(r'<xs:complexType name="',
                           f.read_text(encoding="utf-8", errors="replace")))
        print(f"  {f.name:34s} complexType {n:4d}")
    return 0


def main() -> int:
    cmds = {"types": types, "sample": sample, "counts": counts}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        return 2
    return cmds[sys.argv[1]]()


if __name__ == "__main__":
    raise SystemExit(main())
