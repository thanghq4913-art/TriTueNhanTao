"""simulation.py - Mô phỏng nút giao và so sánh Fixed vs Adaptive (Thành viên 4).

Chạy:  python simulation.py            (dùng data/traffic_data.csv của TV2, tự tạo nếu chưa có)
       python simulation.py --runs 50  (số lần chạy ngẫu nhiên để lấy trung bình)
Xuất:  results.csv, results_average.csv, comparison_chart.png, queue_over_time.png, snapshot.png
"""
import argparse
import csv
import random
from collections import deque

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

from traffic_data import (SCENARIOS, SIMULATION_TIME, TIME_STEP, STORAGE_CAPACITY,
                          get_arrival_rates, poisson_random, calculate_waiting_time,
                          generate_traffic_data, get_default_output_path)
from agent import AdaptiveTrafficAgent
from fixed_signal import FixedSignalController
from metrics import MetricsCollector

SERVICE_RATE = 1.0   # xe/giây khi đèn xanh (2 làn x 0.5) - cùng giả định với phần test trong agent.py
METHODS = {"Fixed": FixedSignalController, "Adaptive": AdaptiveTrafficAgent}


# ---------------------------------------------------------------- dữ liệu vào
def load_arrivals_csv(scenario, csv_path=None):
    """Đọc số xe đến mỗi giây + hàng xe ban đầu từ file CSV của TV2."""
    path = csv_path or get_default_output_path()
    if not path.exists():
        generate_traffic_data(path)
    with path.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["scenario"] == scenario]
    arrivals = [(int(r["arrivals_ns"]), int(r["arrivals_ew"])) for r in rows]
    return arrivals, (int(rows[0]["initial_queue_ns"]), int(rows[0]["initial_queue_ew"]))


def generate_arrivals(scenario, seed):
    """Sinh số xe đến theo cùng mô hình Poisson của TV2 nhưng với seed khác (để chạy nhiều lần)."""
    rng = random.Random(seed)
    out = []
    for t in range(0, SIMULATION_TIME, TIME_STEP):
        r_ns, r_ew = get_arrival_rates(scenario, t)
        out.append((poisson_random(r_ns * TIME_STEP / 60, rng), poisson_random(r_ew * TIME_STEP / 60, rng)))
    c = SCENARIOS[scenario]
    return out, (c["initial_queue_ns"], c["initial_queue_ew"])


# ---------------------------------------------------------------- mô phỏng
def run_simulation(controller, arrivals, initial_queues, service_rate=SERVICE_RATE):
    controller.reset()
    q = {"NS": deque([0] * initial_queues[0]), "EW": deque([0] * initial_queues[1])}
    m = MetricsCollector()
    credit = {"NS": 0.0, "EW": 0.0}
    history = []

    for t, (a_ns, a_ew) in enumerate(arrivals):
        # 1) xe đến (hàng đầy thì xe bị tính là không vào được)
        for d, n in (("NS", a_ns), ("EW", a_ew)):
            for _ in range(n):
                m.record_arrival()
                if len(q[d]) < STORAGE_CAPACITY:
                    q[d].append(t)
                else:
                    m.record_lost()

        # 2) tác tử nhận hàng xe + thời gian chờ của xe đầu hàng, trả về màu đèn
        out = controller.step(queue_ns=len(q["NS"]), queue_ew=len(q["EW"]), dt=TIME_STEP,
                              ext_wait_ns=(t - q["NS"][0]) if q["NS"] else 0,
                              ext_wait_ew=(t - q["EW"][0]) if q["EW"] else 0)
        lights = {"NS": out["ns_light"], "EW": out["ew_light"]}

        # 3) xe rời hàng khi đèn xanh
        for d in ("NS", "EW"):
            if lights[d] == "GREEN":
                credit[d] += service_rate * TIME_STEP
                while credit[d] >= 1 and q[d]:
                    m.record_departure(calculate_waiting_time(q[d].popleft(), t))
                    credit[d] -= 1
            else:
                credit[d] = 0.0

        m.record_queue(len(q["NS"]), len(q["EW"]))
        history.append((t, len(q["NS"]), len(q["EW"]), lights["NS"], lights["EW"]))

    end = len(arrivals)
    remaining = [end - a for d in q for a in q[d]]
    res = m.summary(remaining)
    res["switch_count"] = getattr(controller, "switch_count", 0)
    res["history"] = history
    return res


# ---------------------------------------------------------------- biểu đồ / hình
def plot_comparison(results, path="comparison_chart.png"):
    metrics = [("avg_waiting_time", "Average Waiting Time (s)"),
               ("avg_queue_length", "Average Queue Length (xe)"),
               ("throughput", "Throughput (xe)"),
               ("total_delay", "Total Delay (xe·s)")]
    names = list(results)
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    w = 0.35
    for ax, (key, title) in zip(axes.flat, metrics):
        xs = list(range(len(names)))
        ax.bar([x - w / 2 for x in xs], [results[n]["Fixed"][key] for n in names], w, label="Fixed", color="#d9534f")
        ax.bar([x + w / 2 for x in xs], [results[n]["Adaptive"][key] for n in names], w, label="Adaptive", color="#5cb85c")
        ax.set_xticks(xs); ax.set_xticklabels(names); ax.set_title(title); ax.legend()
    fig.suptitle("So sánh đèn cố định và đèn thích ứng")
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def plot_queue_over_time(res_fixed, res_adaptive, scenario, path="queue_over_time.png"):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, res, name in zip(axes, (res_fixed, res_adaptive), ("Fixed", "Adaptive")):
        h = res["history"]
        ax.plot([x[0] for x in h], [x[1] for x in h], label="Bắc–Nam")
        ax.plot([x[0] for x in h], [x[2] for x in h], label="Đông–Tây")
        ax.set_title(f"{name} - kịch bản {scenario}"); ax.set_xlabel("Thời gian (s)"); ax.legend()
    axes[0].set_ylabel("Số xe chờ")
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def draw_intersection(ax, frame, title):
    """Vẽ nút giao tại một thời điểm: đèn + hàng xe (NS ở nhánh nam, EW ở nhánh tây)."""
    t, q_ns, q_ew, l_ns, l_ew = frame
    col = {"GREEN": "#2ecc40", "YELLOW": "#ffdc00", "RED": "#ff4136"}
    ax.add_patch(Rectangle((-1.2, -10), 2.4, 20, color="#555"))
    ax.add_patch(Rectangle((-10, -1.2), 20, 2.4, color="#555"))
    ax.add_patch(Circle((1.8, -1.9), 0.5, color=col[l_ns]))
    ax.add_patch(Circle((-1.9, 1.8), 0.5, color=col[l_ew]))
    for i in range(min(q_ns, 26)):     # xe Bắc–Nam: 2 làn, xếp lên theo nhánh nam
        ax.add_patch(Rectangle((-0.9 + (i % 2) * 1.0, -2.2 - (i // 2) * 0.6), 0.7, 0.45, color="#0074d9"))
    for i in range(min(q_ew, 26)):     # xe Đông–Tây: 2 làn, xếp theo nhánh tây
        ax.add_patch(Rectangle((-2.2 - (i // 2) * 0.9, -0.9 + (i % 2) * 1.0), 0.7, 0.45, color="#b10dc9"))
    ax.set_xlim(-10, 10); ax.set_ylim(-10, 10); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title(f"{title} | t={t}s | NS={q_ns} xe, EW={q_ew} xe")


def plot_snapshot(res_fixed, res_adaptive, scenario, t=240, path="snapshot.png"):
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.5))
    draw_intersection(axes[0], res_fixed["history"][t], "Fixed")
    draw_intersection(axes[1], res_adaptive["history"][t], "Adaptive")
    fig.suptitle(f"Nút giao - kịch bản {scenario}  (xanh dương: Bắc–Nam, tím: Đông–Tây)")
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


# ---------------------------------------------------------------- main
KEYS = ("avg_waiting_time", "avg_queue_length", "throughput", "total_delay",
        "vehicles_in_queue_at_end", "vehicles_lost", "switch_count")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=30, help="số lần chạy ngẫu nhiên để lấy trung bình")
    args = ap.parse_args()

    # A) chạy trên đúng file CSV của TV2
    results, rows = {}, []
    for name in SCENARIOS:
        arr, init = load_arrivals_csv(name)
        results[name] = {m: run_simulation(cls(), arr, init) for m, cls in METHODS.items()}
        for m, r in results[name].items():
            rows.append({"scenario": name, "method": m, **{k: round(r[k], 2) for k in KEYS}})
    with open("results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    print("=== Kết quả trên traffic_data.csv (1 lần chạy) ===")
    print(f"{'scenario':<8} {'method':<9} {'AvgWait':>8} {'AvgQueue':>9} {'Thru':>5} {'TotalDelay':>11} {'Switch':>6} {'Lost':>5}")
    for r in rows:
        print(f"{r['scenario']:<8} {r['method']:<9} {r['avg_waiting_time']:>8} {r['avg_queue_length']:>9} "
              f"{r['throughput']:>5} {r['total_delay']:>11} {r['switch_count']:>6} {r['vehicles_lost']:>5}")

    # B) chạy nhiều seed để kết quả đáng tin hơn (mỗi lần chỉ có ~100-300 xe)
    avg_rows = []
    for name in SCENARIOS:
        acc = {m: {k: 0.0 for k in KEYS} for m in METHODS}
        for s in range(args.runs):
            arr, init = generate_arrivals(name, 1000 + s)
            for m, cls in METHODS.items():
                r = run_simulation(cls(), arr, init)
                for k in KEYS:
                    acc[m][k] += r[k] / args.runs
        for m in METHODS:
            avg_rows.append({"scenario": name, "method": m, "runs": args.runs,
                             **{k: round(acc[m][k], 2) for k in KEYS}})
    with open("results_average.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(avg_rows[0])); w.writeheader(); w.writerows(avg_rows)

    print(f"\n=== Trung bình {args.runs} lần chạy ===")
    for r in avg_rows:
        print(f"{r['scenario']:<8} {r['method']:<9} {r['avg_waiting_time']:>8} {r['avg_queue_length']:>9} "
              f"{r['throughput']:>7} {r['total_delay']:>11} {r['switch_count']:>6} {r['vehicles_lost']:>5}")

    plot_comparison(results)
    plot_queue_over_time(results["high"]["Fixed"], results["high"]["Adaptive"], "high")
    plot_snapshot(results["high"]["Fixed"], results["high"]["Adaptive"], "high")
    print("\nĐã lưu: results.csv, results_average.csv, comparison_chart.png, queue_over_time.png, snapshot.png")


if __name__ == "__main__":
    main()
