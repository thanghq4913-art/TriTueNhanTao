"""fixed_signal.py - Đèn giao thông chu kỳ cố định (đối chứng) - Thành viên 4.

Cùng giao diện với AdaptiveTrafficAgent: reset(), step(queue_ns, queue_ew, dt) -> dict có ns_light, ew_light.
Chu kỳ: NS xanh -> NS vàng -> (đỏ toàn phần) -> EW xanh -> EW vàng -> (đỏ toàn phần).
Mặc định lấy thông số của TV2 (30s xanh mỗi hướng, 3s vàng); all_red_s=0 đúng như cách TV2 tính đèn đỏ.
"""
from traffic_data import FIXED_GREEN_NS_S, FIXED_GREEN_EW_S, YELLOW_S


class FixedSignalController:
    def __init__(self, green_ns_s=FIXED_GREEN_NS_S, green_ew_s=FIXED_GREEN_EW_S,
                 yellow_s=YELLOW_S, all_red_s=0):
        cycle = [
            ("GREEN", "RED", green_ns_s), ("YELLOW", "RED", yellow_s), ("RED", "RED", all_red_s),
            ("RED", "GREEN", green_ew_s), ("RED", "YELLOW", yellow_s), ("RED", "RED", all_red_s),
        ]
        self.cycle = [c for c in cycle if c[2] > 0]
        self.reset()

    def reset(self):
        self.idx = 0
        self.remaining = self.cycle[0][2]
        self.switch_count = 0

    def step(self, queue_ns=0, queue_ew=0, dt=1, **_ignored):
        """Bỏ qua hàng xe (đèn cố định không nhìn mật độ)."""
        ns_light, ew_light, _ = self.cycle[self.idx]
        self.remaining -= dt
        if self.remaining <= 0:
            self.idx = (self.idx + 1) % len(self.cycle)
            self.remaining = self.cycle[self.idx][2]
            if self.cycle[self.idx][0] == "YELLOW" or self.cycle[self.idx][1] == "YELLOW":
                self.switch_count += 1
        return {"ns_light": ns_light, "ew_light": ew_light}
