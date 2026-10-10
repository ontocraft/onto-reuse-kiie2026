"""공개 온톨로지에서 무엇이 공통이고 무엇이 도메인 전용인지 잰다.

    python scripts/mfg_reuse.py modules    # 모듈별 core 의존
    python scripts/mfg_reuse.py shared     # 여러 모듈이 함께 쓰는 것

여러 제조AI 온톨로지를 만들 때 「무엇을 공통으로 둘 것인가」가 첫 질문이다. IOF 는
그 답을 모듈 구조로 이미 내놓았으므로 먼저 그것을 잰다 (ADR 0028).

⚠️ **재사용 여부를 상위 클래스로 판정한다.** 모듈 파일 안에서 core 이름이 언급되는
   횟수로 세면 공리에 쓰인 것까지 들어와 부풀려진다. `rdfs:subClassOf` 가 core 를
   가리키는 클래스만 센다.
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

SRC = Path("data/ontology/iof-src")
CLS = re.compile(r'<owl:Class[^>]*rdf:about="&iof-[a-z]+;([A-Za-z0-9_]+)"\s*>(.*?)'
                 r'</owl:Class>', re.S)
PROP = re.compile(r'<owl:ObjectProperty[^>]*rdf:about="&iof-[a-z]+;([A-Za-z0-9_]+)"\s*>')
SUP = re.compile(r'<rdfs:subClassOf[^>]*rdf:resource="&(iof-[a-z]+|obo);([A-Za-z0-9_]+)"')


def _core() -> set[str]:
    out: set[str] = set()
    for f in SRC.glob("core__*.rdf"):
        out |= {m[0] for m in CLS.findall(f.read_text(encoding="utf-8", errors="replace"))}
    return out


def modules() -> None:
    if not SRC.is_dir():
        print(f"IOF 배포판이 없다: {SRC}")
        return
    core = _core()
    agg: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    props: collections.Counter = collections.Counter()
    for f in sorted(SRC.glob("*.rdf")):
        mod = f.name.split("__")[0]
        t = f.read_text(encoding="utf-8", errors="replace")
        props[mod] += len(set(PROP.findall(t)))
        if mod == "core":
            continue
        for _, body in CLS.findall(t):
            agg[mod][0] += 1
            if any(x[1] in core for x in SUP.findall(body)):
                agg[mod][1] += 1

    print(f"core 클래스 {len(core)} · object property {props['core']}\n")
    print(f"{'모듈':<22}{'클래스':>7}{'상위가 core':>12}{'비율':>8}{'관계 선언':>10}")
    tn = tc = 0
    for m, (n, c) in sorted(agg.items(), key=lambda x: -x[1][0]):
        tn += n
        tc += c
        print(f"{m:<22}{n:>7}{c:>12}{c/n:>8.0%}{props[m]:>10}")
    print(f"{'합계':<22}{tn:>7}{tc:>12}{tc/tn:>8.0%}")
    print("\n도메인 모듈 클래스의 3 분의 1 이 공통 core 아래 붙는다.")
    print("관계는 반대다. core 가 대부분을 선언하고 도메인 모듈은 거의 더하지 않는다.")


def shared() -> None:
    """여러 도메인 모듈이 함께 상위로 삼는 core 클래스. 공통 후보의 근거다."""
    core = _core()
    by: dict[str, set[str]] = collections.defaultdict(set)
    for f in sorted(SRC.glob("*.rdf")):
        mod = f.name.split("__")[0]
        if mod == "core":
            continue
        for _, body in CLS.findall(f.read_text(encoding="utf-8", errors="replace")):
            for _, tgt in SUP.findall(body):
                if tgt in core:
                    by[tgt].add(mod)
    rows = sorted(((len(v), k, sorted(v)) for k, v in by.items()), reverse=True)
    multi = [r for r in rows if r[0] >= 2]
    print(f"도메인 모듈이 상위로 삼은 core 클래스 {len(rows)} 개")
    print(f"그중 둘 이상의 모듈이 함께 쓰는 것 {len(multi)} 개\n")
    print(f"{'core 클래스':<34}{'모듈 수':>7}  쓰는 모듈")
    for n, k, mods in multi[:20]:
        print(f"{k:<34}{n:>7}  {' · '.join(mods)}")
    print("\n여러 업무가 함께 쓰는 것이 공통 층의 후보다.")


EXT = Path("data/ontology/ext")


def mqto() -> None:
    """MQTO 의 관계를 읽고 우리 스키마와 맞댄다.

        curl -sL -o data/ontology/ext/mqto-1.0.ttl \
          https://raw.githubusercontent.com/dg-assist/mqto/main/mqto-1.0.ttl

    MQTO 는 품질 문제 해결 온톨로지다. 상위 체계가 LIS-14 라 `Specified` 와 `Actual`
    로 유형과 개체를 가르며, **관계도 그 두 층에 쌍으로 둔다.** IOF 는 그렇게 하지
    않으므로 가져올 때 대응을 정해야 한다.
    """
    f = EXT / "mqto-1.0.ttl"
    if not f.exists():
        print(f"파일이 없다: {f}\n  위 docstring 의 curl 명령으로 받는다")
        return
    t = f.read_text(encoding="utf-8")
    blocks = re.findall(r'mqto:(\w+) rdf:type owl:ObjectProperty[^;]*;(.*?)(?=\n\S|\Z)',
                        t, re.S)
    rows = []
    for n, b in blocks:
        d = re.findall(r'rdfs:domain\s+([\w:]+)', b)
        r = re.findall(r'rdfs:range\s+([\w:]+)', b)
        rows.append((n, d[0].split(":")[-1] if d else "", r[0].split(":")[-1] if r else ""))
    cls = sorted(set(re.findall(r'mqto:(\w+) rdf:type owl:Class', t)))
    print(f"클래스 {len(cls)} · 관계 {len(rows)}\n")

    # Specified 와 Actual 어느 층인가
    lvl = {}
    for n, b in re.findall(r'mqto:(\w+) rdf:type owl:Class ;(.*?)(?=\n\S|\Z)', t, re.S):
        sup = re.findall(r'rdfs:subClassOf\s+lis:(\w+)', b)
        if sup:
            lvl[n] = sup[0]
    spec = {k for k, v in lvl.items() if v == "Specified"}
    act = {k for k, v in lvl.items() if v == "Actual"}
    print(f"LIS-14 층: Specified {len(spec)} · Actual {len(act)} · 그 밖 "
          f"{len(cls) - len(spec) - len(act)}")
    print(f"  Specified: {' · '.join(sorted(spec))}")
    print(f"  Actual:    {' · '.join(sorted(act))}\n")

    pairs = [(n, d, r) for n, d, r in rows if d in spec and r in spec]
    apairs = [(n, d, r) for n, d, r in rows if d in act or r in act]
    print(f"유형 층 안에서만 도는 관계 {len(pairs)} · 개체 층이 끼는 관계 {len(apairs)}")
    print("  → 같은 뜻의 관계를 두 층에 쌍으로 둔다. mitigates 와 mitigatedOccurrence 가 그 예다\n")

    print("우리 스키마에 없던 자리를 채우는 관계")
    want = {
        "refersToMetric": "고장이 어떤 지표로 탐지되는가. 우리 「진단한다」의 자리",
        "raisedBy": "고장 발생이 어느 지표 평가에서 나왔는가",
        "readsFrom": "지표가 어느 신호에서 계산되는가",
        "mitigates": "조치가 어떤 고장을 줄이는가",
        "suggested": "추천된 조치. 실제로 완화한 것과 구분한다",
        "failureBelongsTo": "고장이 어느 원인 범주(4M)에 드는가",
    }
    for n, d, r in rows:
        if n in want:
            print(f"  {n:<20}{d:<24}→ {r:<26}{want[n]}")




if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "modules"
    {"modules": modules, "shared": shared, "mqto": mqto}.get(cmd, modules)()
