import csv
import math
import random
from pathlib import Path


# ======================== THONG SO MO PHONG ========================
SIMULATION_TIME = 600          # Giay
TIME_STEP = 1                   # Giay/buoc
RANDOM_SEED = 432

# Gia dinh mo hinh cho moi nhom huong (khong phai so lieu thuc te).
ROAD_LENGTH_M = 200             # Chieu dai doan duong
LANES_PER_DIRECTION = 2
VEHICLE_SPACING_M = 7.5         # Chieu dai xe va khoang cach an toan uoc tinh
STORAGE_CAPACITY = math.floor(ROAD_LENGTH_M / VEHICLE_SPACING_M) * LANES_PER_DIRECTION

# Chu ky dieu khien co dinh de lam doi chung.
FIXED_GREEN_NS_S = 30
FIXED_GREEN_EW_S = 30
YELLOW_S = 3

# Gioi han xanh toi thieu/toi da de nhom AI tham khao.
ADAPTIVE_MIN_GREEN_S = 10
ADAPTIVE_MAX_GREEN_S = 60


# Moi giai doan: (bat dau, ket thuc, luu luong Bac-Nam, luu luong Dong-Tay)
# Luu luong co don vi xe/phut.
SCENARIOS = {
    "low": {
        "initial_queue_ns": 2,
        "initial_queue_ew": 1,
        "periods": [(0, 600, 3, 2)]
    },
    "medium": {
        "initial_queue_ns": 5,
        "initial_queue_ew": 3,
        "periods": [(0, 300, 9, 6), (300, 600, 6, 9)]
    },
    "high": {
        "initial_queue_ns": 10,
        "initial_queue_ew": 7,
        "periods": [(0, 300, 18, 12), (300, 600, 12, 18)]
    }
}


def poisson_random(rate, rng):
    """Sinh so xe den trong mot buoc thoi gian theo phan phoi Poisson."""
    if rate <= 0:
        return 0
    limit = math.exp(-rate)
    product = 1.0
    count = 0
    while product > limit:
        count += 1
        product *= rng.random()
    return count - 1


def get_arrival_rates(scenario, time_step):
    """Lay luu luong xe (xe/phut) cua hai huong tai mot thoi diem."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Kich ban khong hop le: {scenario}")
    for start, end, rate_ns, rate_ew in SCENARIOS[scenario]["periods"]:
        if start <= time_step < end:
            return rate_ns, rate_ew
    raise ValueError(f"Khong co cau hinh {scenario} tai giay {time_step}")


def calculate_density(queue_count, road_length_m=ROAD_LENGTH_M,
                      lanes=LANES_PER_DIRECTION):
    """Mat do hang xe: xe/km/lan. Goi lai voi hang xe hien tai trong simulation."""
    if queue_count < 0 or road_length_m <= 0 or lanes <= 0:
        raise ValueError("So xe phai >= 0; chieu dai va so lan phai > 0")
    return queue_count / ((road_length_m / 1000) * lanes)


def calculate_queue_occupancy(queue_count, capacity=STORAGE_CAPACITY):
    """Ty le lap day suc chua hang xe (%)."""
    if queue_count < 0 or capacity <= 0:
        raise ValueError("So xe phai >= 0 va suc chua phai > 0")
    return queue_count / capacity * 100


def calculate_waiting_time(arrival_time_s, departure_time_s):
    """Thoi gian cho cua mot xe (giay), tinh tu luc den den luc roi hang."""
    if departure_time_s < arrival_time_s:
        raise ValueError("Thoi diem roi hang khong the som hon thoi diem den")
    return departure_time_s - arrival_time_s


def get_default_output_path():
    """Luu data/traffic_data.csv o goc du an; ho tro ca Colab va source_code/."""
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent if script_dir.name.lower() == "source_code" else script_dir
    return project_dir / "data" / "traffic_data.csv"


def validate_config():
    """Kiem tra cac giai doan luu luong va hang xe ban dau."""
    for name, config in SCENARIOS.items():
        for key in ("initial_queue_ns", "initial_queue_ew"):
            if not 0 <= config[key] <= STORAGE_CAPACITY:
                raise ValueError(f"{key} cua {name} vuot gioi han suc chua")
        expected_start = 0
        for start, end, rate_ns, rate_ew in config["periods"]:
            if start != expected_start or end <= start:
                raise ValueError(f"Cac giai doan cua {name} bi ho hoac chong lan")
            if rate_ns < 0 or rate_ew < 0:
                raise ValueError(f"Luu luong cua {name} khong duoc am")
            expected_start = end
        if expected_start != SIMULATION_TIME:
            raise ValueError(f"Cau hinh {name} chua bao phu {SIMULATION_TIME} giay")


def generate_traffic_data(output_file=None, seed=RANDOM_SEED):
    """Tao du lieu dau vao cho ba kich ban va ghi vao file CSV."""
    validate_config()
    output_path = Path(output_file) if output_file else get_default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Den do cua mot huong = xanh cua huong doi dien + vang cua huong doi dien.
    fixed_red_ns_s = FIXED_GREEN_EW_S + YELLOW_S
    fixed_red_ew_s = FIXED_GREEN_NS_S + YELLOW_S

    # Cac cot initial_* la thong so tai thoi diem bat dau, duoc lap lai tren moi dong
    # de cac module khac co the doc mot dong CSV doc lap. Khong khoi tao lai hang xe moi giay.
    columns = [
        "scenario", "time_step_s",
        "arrival_rate_ns_veh_per_min", "arrival_rate_ew_veh_per_min",
        "arrivals_ns", "arrivals_ew",
        "initial_queue_ns", "initial_queue_ew",
        "road_length_m", "lanes_per_direction", "vehicle_spacing_m",
        "storage_capacity_vehicles_per_direction",
        "initial_density_ns_veh_per_km_lane", "initial_density_ew_veh_per_km_lane",
        "initial_occupancy_ns_percent", "initial_occupancy_ew_percent",
        "fixed_green_ns_s", "fixed_green_ew_s",
        "fixed_red_ns_s", "fixed_red_ew_s", "yellow_s",
        "adaptive_min_green_s", "adaptive_max_green_s"
    ]

    totals = {name: {"ns": 0, "ew": 0} for name in SCENARIOS}

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()

        for index, (scenario, config) in enumerate(SCENARIOS.items()):
            rng = random.Random(seed + index)
            queue_ns = config["initial_queue_ns"]
            queue_ew = config["initial_queue_ew"]

            for time_step in range(0, SIMULATION_TIME, TIME_STEP):
                rate_ns, rate_ew = get_arrival_rates(scenario, time_step)
                arrivals_ns = poisson_random(rate_ns * TIME_STEP / 60, rng)
                arrivals_ew = poisson_random(rate_ew * TIME_STEP / 60, rng)
                totals[scenario]["ns"] += arrivals_ns
                totals[scenario]["ew"] += arrivals_ew

                writer.writerow({
                    "scenario": scenario,
                    "time_step_s": time_step,
                    "arrival_rate_ns_veh_per_min": rate_ns,
                    "arrival_rate_ew_veh_per_min": rate_ew,
                    "arrivals_ns": arrivals_ns,
                    "arrivals_ew": arrivals_ew,
                    "initial_queue_ns": queue_ns,
                    "initial_queue_ew": queue_ew,
                    "road_length_m": ROAD_LENGTH_M,
                    "lanes_per_direction": LANES_PER_DIRECTION,
                    "vehicle_spacing_m": VEHICLE_SPACING_M,
                    "storage_capacity_vehicles_per_direction": STORAGE_CAPACITY,
                    "initial_density_ns_veh_per_km_lane": round(calculate_density(queue_ns), 3),
                    "initial_density_ew_veh_per_km_lane": round(calculate_density(queue_ew), 3),
                    "initial_occupancy_ns_percent": round(calculate_queue_occupancy(queue_ns), 2),
                    "initial_occupancy_ew_percent": round(calculate_queue_occupancy(queue_ew), 2),
                    "fixed_green_ns_s": FIXED_GREEN_NS_S,
                    "fixed_green_ew_s": FIXED_GREEN_EW_S,
                    "fixed_red_ns_s": fixed_red_ns_s,
                    "fixed_red_ew_s": fixed_red_ew_s,
                    "yellow_s": YELLOW_S,
                    "adaptive_min_green_s": ADAPTIVE_MIN_GREEN_S,
                    "adaptive_max_green_s": ADAPTIVE_MAX_GREEN_S
                })

    print(f"Da tao du lieu: {output_path}")
    print(f"So dong du lieu: {len(SCENARIOS) * (SIMULATION_TIME // TIME_STEP)}")
    for name, count in totals.items():
        print(f"{name}: Bac-Nam {count['ns']} xe; Dong-Tay {count['ew']} xe")
    return output_path


if __name__ == "__main__":
    generate_traffic_data()
