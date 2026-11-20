"""
Mo-dun tac tu thong minh dieu khien den tin hieu giao thong thich ung (agent.py).
Kien truc: Tac tu phan xa dua tren mo hinh (Model-based Reflex Agent) & toi uu muc tieu.
Phu trach: Thanh vien 3.
"""

import csv
from pathlib import Path

try:
    from traffic_data import (
        ADAPTIVE_MAX_GREEN_S,
        ADAPTIVE_MIN_GREEN_S,
        STORAGE_CAPACITY,
        TIME_STEP,
        YELLOW_S,
        calculate_density,
        calculate_queue_occupancy,
        generate_traffic_data,
        get_default_output_path,
    )
except ImportError:
    # Gia tri du phong dong bo voi traffic_data.py khi chay doc lap
    ROAD_LENGTH_M = 200
    LANES_PER_DIRECTION = 2
    VEHICLE_SPACING_M = 7.5
    STORAGE_CAPACITY = int(ROAD_LENGTH_M // VEHICLE_SPACING_M) * LANES_PER_DIRECTION
    TIME_STEP = 1
    ADAPTIVE_MIN_GREEN_S = 10
    ADAPTIVE_MAX_GREEN_S = 60
    YELLOW_S = 3

    def calculate_density(queue_count, road_length_m=ROAD_LENGTH_M, lanes=LANES_PER_DIRECTION):
        if queue_count < 0 or road_length_m <= 0 or lanes <= 0:
            raise ValueError("So xe phai >= 0; chieu dai va so lan phai > 0")
        return queue_count / ((road_length_m / 1000) * lanes)

    def calculate_queue_occupancy(queue_count, capacity=STORAGE_CAPACITY):
        if queue_count < 0 or capacity <= 0:
            raise ValueError("So xe phai >= 0 va suc chua phai > 0")
        return queue_count / capacity * 100

    def get_default_output_path():
        script_dir = Path(__file__).resolve().parent
        project_dir = script_dir.parent if script_dir.name.lower() == "source_code" else script_dir
        default_path = project_dir / "data" / "traffic_data.csv"
        if default_path.exists():
            return default_path
        local_csv = script_dir / "traffic_data.csv"
        return local_csv if local_csv.exists() else default_path

    generate_traffic_data = None


class AdaptiveTrafficAgent:
    """
    Tac tu dieu khien den tin hieu thich ung su dung bo luat IF-THEN,
    may trang thai an toan 6 pha va co che han che cho qua lau (anti-starvation).
    """

    # 6 trang thai cua may trang thai tin hieu (Signal State Machine)
    NS_GREEN = "NS_GREEN"
    NS_YELLOW = "NS_YELLOW"
    ALL_RED_TO_EW = "ALL_RED_TO_EW"
    EW_GREEN = "EW_GREEN"
    EW_YELLOW = "EW_YELLOW"
    ALL_RED_TO_NS = "ALL_RED_TO_NS"

    def __init__(
        self,
        min_green_s=ADAPTIVE_MIN_GREEN_S,
        max_green_s=ADAPTIVE_MAX_GREEN_S,
        yellow_s=YELLOW_S,
        all_red_s=1,
        queue_diff_threshold=3,
        max_wait_s=45,
        initial_state=NS_GREEN,
    ):
        if min_green_s <= 0 or max_green_s < min_green_s:
            raise ValueError("Tham so xanh toi thieu/toi da khong hop le")
        if yellow_s <= 0 or all_red_s < 0:
            raise ValueError("Tham so thoi gian vang/tat ca do khong hop le")
        if queue_diff_threshold < 0 or max_wait_s <= 0:
            raise ValueError("Nguong chenh lech hoac thoi gian cho toi da khong hop le")

        self.min_green_s = min_green_s
        self.max_green_s = max_green_s
        self.yellow_s = yellow_s
        self.all_red_s = all_red_s
        self.queue_diff_threshold = queue_diff_threshold  # Nguong H
        self.max_wait_s = max_wait_s                      # Nguong W_max
        self.initial_state = initial_state

        self.reset()

    def reset(self):
        """Dat lai trang thai noi tai cua tac tu khi bat dau kich ban moi."""
        self.state = self.initial_state
        self.phase_elapsed_s = 0
        self.wait_ns_s = 0  # Thoi gian truc Bac-Nam dang gap den do va co xe cho
        self.wait_ew_s = 0  # Thoi gian truc Dong-Tay dang gap den do va co xe cho
        self.switch_count = 0

    def _get_light_colors(self):
        """Tra ve mau den (ns_light, ew_light), bao dam hai truc khong bao gio cung GREEN."""
        mapping = {
            self.NS_GREEN: ("GREEN", "RED"),
            self.NS_YELLOW: ("YELLOW", "RED"),
            self.ALL_RED_TO_EW: ("RED", "RED"),
            self.EW_GREEN: ("RED", "GREEN"),
            self.EW_YELLOW: ("RED", "YELLOW"),
            self.ALL_RED_TO_NS: ("RED", "RED"),
        }
        return mapping[self.state]

    def _update_internal_wait_timers(self, queue_ns, queue_ew, dt):
        """Cap nhat bo dem thoi gian cho cua hai pha trong mo hinh noi tai."""
        if self.state == self.NS_GREEN:
            self.wait_ns_s = 0
            self.wait_ew_s = (self.wait_ew_s + dt) if queue_ew > 0 else 0
        elif self.state == self.EW_GREEN:
            self.wait_ew_s = 0
            self.wait_ns_s = (self.wait_ns_s + dt) if queue_ns > 0 else 0
        else:
            # Khi den vang hoac tat ca do, ca hai huong deu dung cho
            self.wait_ns_s = (self.wait_ns_s + dt) if queue_ns > 0 else 0
            self.wait_ew_s = (self.wait_ew_s + dt) if queue_ew > 0 else 0

    def _evaluate_green_rules(self, curr_queue, opp_queue, opp_wait_s):
        """
        Bo luat suy luan IF-THEN quyet dinh giu pha hay chuyen pha khi dang GREEN.
        Tra ve: (should_switch: bool, rule_code: str)
        """
        # Luat 1: Chua du thoi gian xanh toi thieu -> bat buoc giu pha
        if self.phase_elapsed_s < self.min_green_s:
            return False, "HOLD_MIN_GREEN"

        # Luat 2: Da cham thoi gian xanh toi da -> bat buoc chuyen pha
        if self.phase_elapsed_s >= self.max_green_s:
            return True, "SWITCH_MAX_GREEN"

        # Luat 3: Pha doi dien co xe cho vuot nguong W_max -> chuyen pha chong bo doi
        if opp_queue > 0 and opp_wait_s >= self.max_wait_s:
            return True, "SWITCH_MAX_WAIT"

        # Luat 4: Pha hien tai da giai phong het xe trong khi pha kia co xe cho -> chuyen pha
        if curr_queue == 0 and opp_queue > 0:
            return True, "SWITCH_EMPTY_QUEUE"

        # Luat 5: Hang xe pha doi dien nhieu hon pha hien tai vuot nguong H -> chuyen pha
        if (opp_queue - curr_queue) > self.queue_diff_threshold:
            return True, "SWITCH_QUEUE_DIFF"

        # Luat 6: Tiep tuc giu xanh phuc vu pha hien tai
        return False, "HOLD_SERVING"

    def step(self, queue_ns, queue_ew, dt=TIME_STEP, ext_wait_ns=None, ext_wait_ew=None):
        """
        Thuc hien mot buoc Cam nhan -> Suy luan -> Hanh dong cua tac tu.

        Tham so:
            queue_ns (int): So xe dang cho o truc Bac - Nam.
            queue_ew (int): So xe dang cho o truc Dong - Tay.
            dt (int): Buoc thoi gian mo phong (giay).
            ext_wait_ns (float, tuy chon): Thoi gian cho lon nhat cua xe truc NS tu simulation.py.
            ext_wait_ew (float, tuy chon): Thoi gian cho lon nhat cua xe truc EW tu simulation.py.

        Tra ve:
            dict: Trang thai tin hieu, mau den hai huong, ly do quyet dinh va mat do hien tai.
        """
        if queue_ns < 0 or queue_ew < 0:
            raise ValueError("So xe cho khong duoc am")

        self.phase_elapsed_s += dt
        self._update_internal_wait_timers(queue_ns, queue_ew, dt)

        effective_wait_ns = ext_wait_ns if ext_wait_ns is not None else self.wait_ns_s
        effective_wait_ew = ext_wait_ew if ext_wait_ew is not None else self.wait_ew_s

        decision = "KEEP"
        reason = "IN_TRANSITION"

        # May trang thai chuyen pha an toan
        if self.state == self.NS_GREEN:
            should_switch, reason = self._evaluate_green_rules(
                curr_queue=queue_ns,
                opp_queue=queue_ew,
                opp_wait_s=effective_wait_ew,
            )
            if should_switch:
                self.state = self.NS_YELLOW
                self.phase_elapsed_s = 0
                self.switch_count += 1
                decision = "SWITCH_TO_YELLOW"

        elif self.state == self.NS_YELLOW:
            if self.phase_elapsed_s >= self.yellow_s:
                if self.all_red_s > 0:
                    self.state = self.ALL_RED_TO_EW
                    reason = "YELLOW_TO_ALL_RED"
                else:
                    self.state = self.EW_GREEN
                    reason = "YELLOW_TO_EW_GREEN"
                self.phase_elapsed_s = 0
                decision = "TRANSITION"

        elif self.state == self.ALL_RED_TO_EW:
            if self.phase_elapsed_s >= self.all_red_s:
                self.state = self.EW_GREEN
                self.phase_elapsed_s = 0
                decision = "ACTIVATE_EW_GREEN"
                reason = "ALL_RED_DONE"

        elif self.state == self.EW_GREEN:
            should_switch, reason = self._evaluate_green_rules(
                curr_queue=queue_ew,
                opp_queue=queue_ns,
                opp_wait_s=effective_wait_ns,
            )
            if should_switch:
                self.state = self.EW_YELLOW
                self.phase_elapsed_s = 0
                self.switch_count += 1
                decision = "SWITCH_TO_YELLOW"

        elif self.state == self.EW_YELLOW:
            if self.phase_elapsed_s >= self.yellow_s:
                if self.all_red_s > 0:
                    self.state = self.ALL_RED_TO_NS
                    reason = "YELLOW_TO_ALL_RED"
                else:
                    self.state = self.NS_GREEN
                    reason = "YELLOW_TO_NS_GREEN"
                self.phase_elapsed_s = 0
                decision = "TRANSITION"

        elif self.state == self.ALL_RED_TO_NS:
            if self.phase_elapsed_s >= self.all_red_s:
                self.state = self.NS_GREEN
                self.phase_elapsed_s = 0
                decision = "ACTIVATE_NS_GREEN"
                reason = "ALL_RED_DONE"

        ns_light, ew_light = self._get_light_colors()

        return {
            "state": self.state,
            "ns_light": ns_light,
            "ew_light": ew_light,
            "phase_elapsed_s": self.phase_elapsed_s,
            "decision": decision,
            "reason": reason,
            "density_ns": round(calculate_density(queue_ns), 3),
            "density_ew": round(calculate_density(queue_ew), 3),
            "occupancy_ns": round(calculate_queue_occupancy(queue_ns), 2),
            "occupancy_ew": round(calculate_queue_occupancy(queue_ew), 2),
        }


# ======================== KIEM THU VOI FILE CUA THANH VIEN 2 ========================
if __name__ == "__main__":
    csv_path = get_default_output_path()
    if not csv_path.exists():
        if generate_traffic_data is not None:
            generate_traffic_data(csv_path)
        else:
            raise FileNotFoundError(
                f"Khong tim thay file du lieu tai {csv_path}. "
                "Vui long chay traffic_data.py truoc."
            )

    for scenario_name in ("low", "medium", "high"):
        with csv_path.open("r", encoding="utf-8") as file:
            rows = [r for r in csv.DictReader(file) if r["scenario"] == scenario_name]

        agent = AdaptiveTrafficAgent()
        q_ns = int(rows[0]["initial_queue_ns"])
        q_ew = int(rows[0]["initial_queue_ew"])
        service_rate = 1  # Gia dinh giai phong toi da 1 xe/giay khi den xanh

        for row in rows:
            q_ns = min(STORAGE_CAPACITY, q_ns + int(row["arrivals_ns"]))
            q_ew = min(STORAGE_CAPACITY, q_ew + int(row["arrivals_ew"]))

            out = agent.step(queue_ns=q_ns, queue_ew=q_ew, dt=TIME_STEP)

            if out["ns_light"] == "GREEN":
                q_ns = max(0, q_ns - service_rate)
            elif out["ew_light"] == "GREEN":
                q_ew = max(0, q_ew - service_rate)

        print(
            f"Kich ban {scenario_name:6s} | So lan chuyen pha: {agent.switch_count:2d} | "
            f"Hang xe cuoi: NS={q_ns}, EW={q_ew}"
        )
