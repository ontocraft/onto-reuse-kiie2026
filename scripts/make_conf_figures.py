"""학회 8 쪽 판에 넣을 그림을 측정 파일에서 바로 그린다.

    python scripts/make_conf_figures.py

⚠️ **숫자를 손으로 옮기지 않는다.** 그림 1 은 `mfg_cover.py` 의 X1 배정과 QIF 표본에서
   읽고 요소가 다르면 멈춘다. 그림 2 는 QIF 배포판 xsd 와 측정 표본에서 직접
   읽는다. 그림 3 은 `data/mfg/대조-단계.json` 을 읽되 **마지막 단계를
   `mfg_cover.py` 와 맞춰 보고 다르면 멈춘다.**

⚠️ 그림 3 은 동일 기준 성능 비교가 아닌 조사 기록이다. 1~5 단계는 당시 기록한
   값이며 과거 상태를 재측정할 수 없다.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                       # noqa: E402
from matplotlib import font_manager                   # noqa: E402

OUT = Path("figures")
STAGES = Path("data/mfg/대조-단계.json")

KO = next((n for n in ("AppleGothic", "Apple SD Gothic Neo", "NanumGothic",
                       "Malgun Gothic")
           if n in {f.name for f in font_manager.fontManager.ttflist}), None)
if KO:
    plt.rcParams["font.family"] = KO
plt.rcParams["axes.unicode_minus"] = False


def _qif():
    spec = importlib.util.spec_from_file_location("q", "scripts/mfg_qif.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def fig1() -> None:
    """선정한 다섯 타입의 직접 선언 필드와 공개 표본에서 관측한 필드."""
    q = _qif()
    import xml.etree.ElementTree as ET
    NS = "{http://qifstandards.org/xsd/qif3}"
    # ⚠️ `/tmp` 는 지워진다. 저장소의 `data/ontology/ext` 를 먼저 본다
    samples = sorted(q.EXT.glob("*.qif")) or sorted(Path("/tmp").glob("*.qif"))
    if not samples:
        sys.exit("표본이 없다. mfg_qif.py 머리말의 명령으로 받아 "
                 "data/ontology/ext 에 둔다")
    rows = []
    for fn, tn, what, suffix in q.WANT:
        decl = q.fields(q.EXT / fn, tn)
        if decl is None:
            sys.exit(f"{tn} 을 읽지 못했다. 배포판을 받는다")
        kids: set[str] = set()
        for s in samples:
            root = ET.parse(s).getroot()
            for e in root.iter():
                if e.tag.replace(NS, "").endswith(suffix):
                    kids.update(c.tag.replace(NS, "") for c in e)
        got = sum(1 for n, _, _ in decl if n in kids)
        rows.append((tn.replace("BaseType", "").replace("Type", ""), len(decl), got))

    fig, ax = plt.subplots(figsize=(6.0, 2.6))
    y = range(len(rows))
    ax.barh([i + 0.0 for i in y], [r[1] for r in rows], height=0.62,
            color="#d9d9d9", edgecolor="#555", linewidth=0.6, label="스키마의 직접 선언 필드")
    ax.barh([i + 0.0 for i in y], [r[2] for r in rows], height=0.62,
            color="#404040", edgecolor="#222", linewidth=0.6, label="공개 표본에서 관측한 필드")
    for i, (_, d, g) in enumerate(rows):
        ax.text(d + 0.4, i, f"{g} / {d}", va="center", fontsize=8)
    ax.set_yticks(list(y)); ax.set_yticklabels([r[0] for r in rows], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("필드 수", fontsize=9)
    ax.set_xlim(0, max(r[1] for r in rows) + 6)
    # 범례가 막대를 가리지 않도록 빈 자리(위쪽 오른편)에 둔다
    ax.legend(fontsize=8, loc="upper right", frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    tot_d = sum(r[1] for r in rows); tot_g = sum(r[2] for r in rows)
    ax.set_title(f"선정한 5개 타입의 직접 선언 필드 {tot_d}개 중 표본에서 {tot_g}개 관측",
                 fontsize=10, loc="left")
    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "그림2-정의와-자료.png", dpi=200)
    print(f"그림 2 저장. 직접 선언 필드 {tot_d} · 관측 필드 {tot_g} · 표본 {len(samples)} 개")


def fig2() -> None:
    """동일 기준 성능 비교가 아닌 조사 기록이며 1~5단계는 재측정할 수 없다.

    마지막 단계의 기록값만 현재 mfg_cover.py 출력과 대조한다.
    """
    d = json.loads(STAGES.read_text(encoding="utf-8"))
    st = d["단계"]
    out = subprocess.run([sys.executable, "scripts/mfg_cover.py"],
                         capture_output=True, text=True).stdout
    m = re.search(r"요구 요소 대응 (\d+) · 부분 (\d+) · 대응 없음 (\d+)", out)
    if not m:
        sys.exit("mfg_cover.py 출력에서 값을 읽지 못했다")
    live = tuple(int(x) for x in m.groups())
    last = (st[-1]["대응"], st[-1]["부분"], st[-1]["없음"])
    if live != last:
        sys.exit(f"마지막 단계가 지금 값과 다르다. 기록 {last} · 지금 {live}. "
                 f"{STAGES} 를 고친다")

    fig, ax = plt.subplots(figsize=(6.0, 2.8))
    x = [s["n"] for s in st]
    width = 0.23
    # 선 그래프는 비교할 수 없는 단계별 기록을 상승 추세처럼 보이게 한다.
    # 세 분류를 단계 안에서만 비교하고, 흑백 인쇄에서도 무늬로 구분한다.
    for key, offset, color, hatch, label in (
        ("대응", -width, "#343434", "", "재사용 후보 배정"),
        ("부분", 0, "#a0a0a0", "///", "부분 배정"),
        ("없음", width, "#ffffff", "xx", "미배정"),
    ):
        bars = ax.bar([n + offset for n in x], [s[key] for s in st],
                      width=width, color=color, hatch=hatch, edgecolor="#242424",
                      linewidth=0.7, label=label)
        for bar, s in zip(bars, st):
            value = s[key]
            ax.annotate(str(value),
                        (bar.get_x() + bar.get_width() / 2, value),
                        xytext=(0, 2), textcoords="offset points",
                        ha="center", va="bottom", fontsize=7.5)
    ax.set_xlim(0.45, 6.55)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{s['n']}단계\n{s['요소']}개" for s in st], fontsize=8)
    ax.set_xlabel("조사 단계 · 단계마다 조사 범위가 다름", fontsize=9)
    ax.set_ylabel("질문 수 (전체 26개)", fontsize=9)
    ax.set_ylim(0, 26)
    ax.legend(fontsize=8, frameon=False, loc="upper left", ncol=3,
              columnspacing=0.9, handlelength=1.2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("조사 단계별 재사용 후보 요소 배정 기록",
                 fontsize=10, loc="left")
    fig.text(0.52, 0.012, "1~5단계: 당시 기록(재측정 불가) · 6단계: 현재 값 대조",
             ha="center", fontsize=7.5)
    fig.tight_layout(rect=(0, 0.055, 1, 1))
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "그림3-여섯-단계.png", dpi=200)
    print(f"그림 3 저장. 마지막 단계가 지금 값과 같다 {live}")


def fig3() -> None:
    """실행 예 X1 의 사슬. 어디가 공개 정의이고 어디에 값이 없고 어디가 끊겼나.

    ⚠️ 요소는 `mfg_cover.py` 의 X1 배정에서, 출처는 스키마 JSON 에서, 표본 건수는
       QIF 표본에서 읽는다. 그림에 그린 요소가 X1 배정과 다르면 멈춘다.
    """
    import matplotlib.patches as mp
    import xml.etree.ElementTree as ET
    spec = importlib.util.spec_from_file_location("c", "scripts/mfg_cover.py")
    cov = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cov)
    x1 = next(v[0] for k, v in cov.NEED.items() if k.startswith("X1 "))

    schema = json.loads(Path("schema/제조-공통스키마.json").read_text(encoding="utf-8"))
    src: dict[str, str] = {}

    def walk(o):
        if isinstance(o, dict):
            if "이름" in o:
                if o.get("IOF"):
                    src[o["이름"]] = f"IOF {o.get('모듈')}"
                elif o.get("출처") == "품질":
                    src[o["이름"]] = "QIF"
                else:
                    src[o["이름"]] = "추가"
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(schema)

    q = _qif()
    NS = "{http://qifstandards.org/xsd/qif3}"
    samples = sorted(q.EXT.glob("*.qif"))
    if not samples:
        sys.exit("표본이 없다")
    n_meas, n_proc, has_pid = [], [], []
    for s in samples:
        root = ET.parse(s).getroot()
        meas = [e for e in root.iter()
                if e.tag.replace(NS, "").endswith("CharacteristicMeasurement")]
        n_meas.append(len(meas))
        n_proc.append(sum(1 for e in root.iter() if e.tag.replace(NS, "")
                          .endswith("ManufacturingProcessTraceability")))
        has_pid.append(sum(1 for e in meas for c in e
                           if c.tag.replace(NS, "") == "ManufacturingProcessId"))

    # (요소 이름들, 표시 이름, 원 이름, 표본 상태) — 상자
    boxes = [
        (["특성 측정"], "특성 측정·적합 판정",
         "QIF CharacteristicMeasurement",
         f"표본 {n_meas[0]} · {n_meas[1]}건", "obs"),
        (["공정 실행 기록", "이전 공정이다"], "공정 실행 기록",
         "QIF ManufacturingProcessTraceability",
         f"표본 {n_proc[0]} · {n_proc[1]}건", "none"),
        (["재료 인공물", "역할을 가진다", "정비 대상 역할"], "물질 인공물 + 정비 대상 역할",
         "IOF MaterialArtifact · hasRole", "인스턴스 미적재", "def"),
        (["정비 상태"], "정비 상태", "IOF MaintenanceState", "인스턴스 미적재", "def"),
    ]
    # (요소 이름, 표시 이름, 원 이름, 상태) — 화살표
    edges = [
        ("공정을 가리킨다", "공정을 가리킨다", "QIF ManufacturingProcessId",
         f"표본 {has_pid[0]} · {has_pid[1]}건", "none"),
        ("설비를 가리킨다", "설비를 가리킨다", "공개 정의 없음 · QIF는 문자열",
         "본 연구가 추가", "cut"),
        ("정비 상태를 가진다", "정비 상태를 가진다", "IOF hasMaintenanceState",
         "", "def"),
    ]
    drawn = {n for b in boxes for n in b[0]} | {e[0] for e in edges}
    if drawn != set(x1):
        sys.exit(f"그림 1 요소가 X1 배정과 다르다. 빠짐 {set(x1) - drawn} · "
                 f"남음 {drawn - set(x1)}")
    for n in drawn:
        want = "추가" if n == "설비를 가리킨다" else None
        if want and src.get(n) != want:
            sys.exit(f"{n} 의 출처가 스키마와 다르다: {src.get(n)}")
        if n != "설비를 가리킨다" and src.get(n) == "추가":
            sys.exit(f"{n} 이 스키마에서 공개 정의가 없는 요소로 되어 있다")

    fig, ax = plt.subplots(figsize=(6.6, 2.5))
    ax.set_xlim(-1.5, 101.5); ax.set_ylim(0, 34); ax.axis("off")
    # 화살표의 이름은 상자 위 띠에, 표본 상태는 상자 아래 띠에 둔다. 상자와 겹치지 않는다
    w, h, y0 = 18.5, 14.0, 10.0
    gap = (100 - 4 * w) / 3
    xs = [i * (w + gap) for i in range(4)]
    style = {"obs": ("#ffffff", ""), "none": ("#ffffff", "////"), "def": ("#e4e4e4", "")}
    for x, (_, title, orig, note, kind) in zip(xs, boxes):
        fc, hatch = style[kind]
        ax.add_patch(mp.FancyBboxPatch((x, y0), w, h, boxstyle="round,pad=0.25",
                                       fc=fc, ec="#222", lw=0.8, hatch=hatch))
        white = dict(fc="white", ec="none", pad=0.5)
        ax.text(x + w / 2, y0 + h - 3.6, title.replace(" + ", "\n+ "), ha="center",
                va="center", fontsize=7.0, linespacing=1.1, bbox=white)
        ax.text(x + w / 2, y0 + h / 2 - 1.6, orig.replace(" ", "\n", 1), ha="center",
                va="center", fontsize=5.6, linespacing=1.1, bbox=white)
        ax.text(x + w / 2, y0 + 1.9, note, ha="center", va="center", fontsize=6.2,
                bbox=white)
    for i, (_, title, orig, note, kind) in enumerate(edges):
        x_a, x_b = xs[i] + w + 0.6, xs[i + 1] - 0.6
        ym = y0 + h / 2
        ax.annotate("", xy=(x_b, ym), xytext=(x_a, ym),
                    arrowprops=dict(arrowstyle="-|>", lw=1.1, color="#222",
                                    linestyle=(0, (2.5, 2)) if kind == "cut" else "-"))
        xm = (x_a + x_b) / 2
        ax.text(xm, 31.0, title, ha="center", va="center", fontsize=6.4)
        ax.text(xm, 28.0, orig, ha="center", va="center", fontsize=6.0, color="#333")
        ax.plot([xm, xm], [26.6, ym + 0.8], color="#888", lw=0.5)
        if note:
            ax.plot([xm, xm], [ym - 0.8, 6.4], color="#888", lw=0.5)
            ax.text(xm, 4.6, note, ha="center", va="center", fontsize=5.8,
                    bbox=dict(fc="white", ec="#222", lw=0.5, pad=0.7))
    # 범례
    leg = [mp.Patch(fc="#ffffff", ec="#222", label="공개 정의 · 표본에 값 있음"),
           mp.Patch(fc="#ffffff", ec="#222", hatch="////", label="공개 정의 · 표본에 값 없음"),
           mp.Patch(fc="#e4e4e4", ec="#222", label="공개 정의 · 인스턴스 미적재"),
           plt.Line2D([], [], color="#222", lw=1.1, linestyle=(0, (2.5, 2)),
                      label="공개 정의 없는 연결")]
    ax.legend(handles=leg, loc="lower center", ncol=4, fontsize=6.5, frameon=False,
              bbox_to_anchor=(0.5, -0.16), handlelength=1.6, columnspacing=1.0)
    fig.tight_layout(pad=0.2)
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "그림1-실행-예.png", dpi=220)
    print(f"그림 1 저장. X1 요소 {len(x1)} · 측정 {n_meas} · 공정 실행 기록 {n_proc} · "
          f"측정의 공정 참조 {has_pid}")


if __name__ == "__main__":
    if not KO:
        print("⚠️ 한글 폰트를 찾지 못했다. 이름이 깨질 수 있다")
    fig1(); fig2(); fig3()
