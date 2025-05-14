# Chat-gpt estimates
# energy is kwh/
GPU_INFO = {
    "T4": {
        "energy": 0.012,
        "nvidia_driver": "sm_75",
        "price_per_sec": 0.000164,
        "electricity_cost_per_sec": 0.012 * 0.12 / 3600,
    },
    "L4": {
        "energy": 0.009,
        "nvidia_driver": "sm_89",
        "price_per_sec": 0.000222,
        "electricity_cost_per_sec": 0.009 * 0.12 / 3600,
    },
    "A10G": {
        "energy": 0.020,
        "nvidia_driver": "sm_86",
        "price_per_sec": 0.000306,
        "electricity_cost_per_sec": 0.020 * 0.12 / 3600,
    },
    "A100-40GB": {
        "energy": 0.035,
        "nvidia_driver": "sm_80",
        "price_per_sec": 0.000583,
        "electricity_cost_per_sec": 0.035 * 0.12 / 3600,
    },
    "A100-80GB": {
        "energy": 0.040,
        "nvidia_driver": "sm_80",
        "price_per_sec": 0.000694,
        "electricity_cost_per_sec": 0.040 * 0.12 / 3600,
    },
    "L40S": {
        "energy": 0.030,
        "nvidia_driver": "sm_89",
        "price_per_sec": 0.000542,
        "electricity_cost_per_sec": 0.030 * 0.12 / 3600,
    },
    "H100": {
        "energy": 0.050,
        "nvidia_driver": "sm_90",
        "price_per_sec": 0.001097,
        "electricity_cost_per_sec": 0.050 * 0.12 / 3600,
    },
}
