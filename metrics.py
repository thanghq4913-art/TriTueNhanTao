"""metrics.py - Tính các chỉ số đánh giá (Thành viên 4)."""


class MetricsCollector:
    def __init__(self):
        self.waits = []            # thời gian chờ của từng xe đã qua nút giao (giây)
        self.queue_samples = []    # (hàng NS, hàng EW) mỗi bước
        self.arrived = 0
        self.lost = 0              # xe không vào được vì hàng đã đầy sức chứa

    def record_arrival(self):
        self.arrived += 1

    def record_lost(self):
        self.lost += 1

    def record_departure(self, wait_time):
        self.waits.append(wait_time)

    def record_queue(self, queue_ns, queue_ew):
        self.queue_samples.append((queue_ns, queue_ew))

    def summary(self, remaining_waits=()):
        """remaining_waits: thời gian chờ (đến lúc kết thúc) của xe còn kẹt trong hàng."""
        all_waits = list(self.waits) + list(remaining_waits)
        n = len(all_waits)
        total_delay = sum(all_waits)
        steps = len(self.queue_samples) or 1
        return {
            "avg_waiting_time": total_delay / n if n else 0.0,                      # giây/xe
            "avg_queue_length": sum(a + b for a, b in self.queue_samples) / steps,  # xe (cả 2 hướng)
            "throughput": len(self.waits),                                          # xe đã thông qua
            "total_delay": total_delay,                                             # xe·giây
            "vehicles_in_queue_at_end": len(remaining_waits),
            "vehicles_lost": self.lost,
        }
