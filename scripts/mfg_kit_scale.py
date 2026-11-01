"""합성 자료로 키트의 규모를 시험한다. 측정 1천 · 1만 건에서 적재와 X1 시간을 잰다.

    python scripts/mfg_kit_scale.py

**왜 만들었나.** 예제는 측정 1,050 건, NIST 는 1,748 건이다. 「더 큰 자료에서도 되는가」에
답이 없었다(2026-10-12). 합성 자료라 답의 값에는 뜻이 없고 시간만 본다.

만드는 자료: 부품 수 = 측정 / 10, 공정 실행 = 부품 수, 설비 20 대(문자열 둘씩), 설비마다
정비 상태 5 구간, 부적합 비율 10%. rdflib 메모리 그래프에서 잰다. 운영 Neo4j 에 닿지 않는다.

**2026-11-02 추가.** 같은 그래프를 Oxigraph(pyoxigraph, Rust 로 만든 RDF 저장소) 메모리
저장소에 옮겨 같은 X1 질의를 잰다. 185 초가 질의 구조 탓인지 rdflib 탓인지를 가르려는 것이다.
두 저장소의 답 개수가 같은지도 함께 본다.
"""
from __future__ import annotations

import csv
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mfg_kit as kit  # noqa: E402

SIZES = [1_000, 10_000]


def oxigraph_x1(g):
    """rdflib 그래프를 N-Triples 로 옮겨 Oxigraph 에서 X1 을 잰다. (옮기는 시간, 질의 시간, 답 수)"""
    import pyoxigraph as ox
    t = time.perf_counter()
    store = ox.Store()
    # bulk_load 는 파일을 나눠 병렬로 읽어 같은 빈 노드가 서로 다른 노드가 된다. 그러면 시각 값(빈 노드)
    # 으로 가는 조인이 끊겨 X1 이 1,017 건 대신 48 건을 낸다(2026-11-02 실측). load 를 쓴다
    store.load(g.serialize(format="nt", encoding="utf-8"), ox.RdfFormat.N_TRIPLES)
    t_load = time.perf_counter() - t
    head = "".join(f"PREFIX {k}: <{v}>\n" for k, v in kit.PREFIX.items())
    t = time.perf_counter()
    n = len(list(store.query(head + kit.X1)))
    return t_load, time.perf_counter() - t, n


def make(dirpath: Path, n_meas: int) -> None:
    rng = random.Random(n_meas)
    dirpath.mkdir(parents=True, exist_ok=True)
    n_parts = max(n_meas // 10, 1)
    t0 = datetime(2026, 1, 1)
    with open(dirpath / "measurements.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["model_number", "serial_number", "characteristic", "value", "status"])
        for i in range(n_meas):
            w.writerow(["P1", f"S{i % n_parts}", "Diameter", f"{rng.random():.4f}",
                        "FAIL" if rng.random() < 0.1 else "PASS"])
    with open(dirpath / "mes_process_runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["model_number", "serial_number", "run_id", "operation", "machine_id",
                    "operator_id", "start", "end"])
        for i in range(n_parts):
            st = t0 + timedelta(minutes=5 * i)
            w.writerow(["P1", f"S{i}", f"R{i}", "milling", f"M-{i % 20:02d}", f"OP-{i % 7}",
                        st.isoformat(timespec="minutes"), (st + timedelta(minutes=4)).isoformat(timespec="minutes")])
    with open(dirpath / "equipment_registry.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["equipment_id", "identifier", "system", "kind", "roles"])
        for k in range(20):
            w.writerow([f"mc{k:02d}", f"M-{k:02d}", "MES", "mc", "equipment;maintainable"])
            w.writerow([f"mc{k:02d}", f"MC{k:03d}", "CMMS", "mc", "equipment;maintainable"])
    span = timedelta(minutes=5 * n_parts) / 5
    with open(dirpath / "maintenance_states.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["identifier", "state", "start", "end", "work_order"])
        for k in range(20):
            for j in range(5):
                st = t0 + span * j
                w.writerow([f"MC{k:03d}", ["Operating", "Degraded", "Operating", "Failed", "Operating"][j],
                            st.isoformat(timespec="minutes"),
                            (st + span).isoformat(timespec="minutes") if j < 4 else "", ""])


def main() -> int:
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/kit-scale")
    print(f"{'측정':>7s} {'트리플':>8s} {'적재(s)':>8s} {'분류(s)':>8s} {'X1(s)':>7s} {'X1 답':>7s}"
          f" {'Ox 옮김(s)':>10s} {'Ox X1(s)':>9s} {'Ox 답':>6s}")
    for n in SIZES:
        d = base / str(n)
        make(d, n)
        t = time.perf_counter()
        g, rules, closure = kit.build(d, [])
        t_load = time.perf_counter() - t
        t = time.perf_counter()
        kit.materialize(g, rules, closure)
        t_mat = time.perf_counter() - t
        t = time.perf_counter()
        answers = len(list(g.query(kit.X1, initNs=kit.PREFIX)))
        t_q = time.perf_counter() - t
        ox_load, ox_q, ox_n = oxigraph_x1(g)
        print(f"{n:7d} {len(g):8d} {t_load:8.1f} {t_mat:8.1f} {t_q:7.1f} {answers:7d}"
              f" {ox_load:10.2f} {ox_q:9.3f} {ox_n:6d}")
    print("⚠️ 합성 자료다. 답의 값에는 뜻이 없다. X1 은 rdflib 메모리 그래프, Ox 는 Oxigraph 메모리 저장소의 시간이다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
