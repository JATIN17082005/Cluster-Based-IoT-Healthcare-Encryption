"""Authoritative metrics calculation module.
Implements:
1. Exact percentage change and energy savings from unrounded raw values.
2. Result status classification (IMPROVEMENT, REGRESSION, INCONCLUSIVE).
3. Monotonic timing statistics and multi-repetition variability (mean, median, p95, min, max, std_dev).
4. Transmission metrics (TSR: Transmission Success Rate, PLR: Packet Loss Rate).
5. Numerical trapezoidal energy integration (J, mJ/record, mJ/1000 records, mWh).
6. Indicative battery runtime and battery charge consumed (mAh).
"""

import math
from typing import List, Dict, Any, Optional, Tuple
from src.models import MeasurementSource


def calculate_percentage_change(baseline: float, proposed: float) -> float:
    """Calculate percentage change from unrounded raw values:
    Percentage change = ((Proposed - Baseline) / Baseline) * 100

    Positive percentage change means an increase.
    Negative percentage change means a reduction.
    Returns 0.0 if baseline is zero.
    """
    if baseline == 0.0:
        return 0.0
    return ((proposed - baseline) / abs(baseline)) * 100.0


def calculate_energy_saving(baseline_energy: float, proposed_energy: float) -> float:
    """Calculate percentage energy saving from unrounded raw values:
    Percentage energy saving = ((Baseline Energy - Proposed Energy) / Baseline Energy) * 100

    Positive percentage saving means a reduction (energy saved).
    Negative percentage saving means an increase (more energy consumed / regression).
    Returns 0.0 if baseline_energy is zero.
    """
    if baseline_energy == 0.0:
        return 0.0
    return ((baseline_energy - proposed_energy) / abs(baseline_energy)) * 100.0


def evaluate_result_status(
    baseline: float,
    proposed: float,
    lower_is_better: bool = True,
    noise_threshold_pct: float = 0.2,
) -> str:
    """Evaluate whether comparative result represents IMPROVEMENT, REGRESSION, or INCONCLUSIVE.
    Considers noise margin for micro-variations.
    """
    if baseline == 0.0:
        if proposed == 0.0:
            return "INCONCLUSIVE"
        return "REGRESSION" if lower_is_better else "IMPROVEMENT"

    pct_diff = ((proposed - baseline) / abs(baseline)) * 100.0

    if abs(pct_diff) < noise_threshold_pct:
        return "INCONCLUSIVE"

    if lower_is_better:
        return "IMPROVEMENT" if pct_diff < 0 else "REGRESSION"
    else:
        return "IMPROVEMENT" if pct_diff > 0 else "REGRESSION"


def compute_timing_stats(timings_ms: List[float]) -> Tuple[float, float, float, float]:
    """Compute mean, median, p95, and total from a list of timing measurements in milliseconds.
    Returns: (mean_ms, median_ms, p95_ms, total_ms)
    """
    if not timings_ms:
        return 0.0, 0.0, 0.0, 0.0

    sorted_t = sorted(timings_ms)
    n = len(sorted_t)
    total_ms = sum(sorted_t)
    mean_ms = total_ms / n

    # Median
    if n % 2 == 1:
        median_ms = sorted_t[n // 2]
    else:
        median_ms = (sorted_t[n // 2 - 1] + sorted_t[n // 2]) / 2.0

    # P95 (Nearest rank)
    p95_index = max(0, math.ceil(0.95 * n) - 1)
    p95_ms = sorted_t[p95_index]

    return round(mean_ms, 6), round(median_ms, 6), round(p95_ms, 6), round(total_ms, 6)


def compute_aggregate_stats(values: List[float]) -> Dict[str, float]:
    """Compute comprehensive multi-run distribution statistics (mean, median, p95, min, max, std_dev, spread)."""
    if not values:
        return {
            "mean": 0.0,
            "median": 0.0,
            "p95": 0.0,
            "min": 0.0,
            "max": 0.0,
            "std_dev": 0.0,
            "spread": 0.0,
        }

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mean_val = sum(sorted_vals) / n

    if n % 2 == 1:
        median_val = sorted_vals[n // 2]
    else:
        median_val = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0

    p95_idx = max(0, math.ceil(0.95 * n) - 1)
    p95_val = sorted_vals[p95_idx]

    min_val = sorted_vals[0]
    max_val = sorted_vals[-1]
    spread = max_val - min_val

    if n > 1:
        variance = sum((x - mean_val) ** 2 for x in sorted_vals) / (n - 1)
        std_dev = math.sqrt(variance)
    else:
        std_dev = 0.0

    return {
        "mean": mean_val,
        "median": median_val,
        "p95": p95_val,
        "min": min_val,
        "max": max_val,
        "std_dev": std_dev,
        "spread": spread,
    }


def compute_tsr(records_sent: int, records_accepted: int) -> float:
    """Calculate Transmission Success Rate (TSR):
    TSR = successfully received and verified records / records sent * 100%
    Handles zero denominator safely.
    """
    if records_sent <= 0:
        return 0.0
    return round((records_accepted / records_sent) * 100.0, 2)


def compute_plr(records_sent: int, records_received: int) -> float:
    """Calculate Packet Loss Rate (PLR):
    PLR = records sent but not received / records sent * 100%
    Handles zero denominator safely.
    """
    if records_sent <= 0:
        return 0.0
    lost = max(0, records_sent - records_received)
    return round((lost / records_sent) * 100.0, 2)


def integrate_energy_joules(
    voltage_v_samples: List[float],
    current_ma_samples: List[float],
    timestamps_ms: List[float],
) -> Tuple[float, float, float, float]:
    """Integrate power over time using trapezoidal numerical integration.
    Energy (J) = sum [ voltage(V) * current(A) * dt(s) ]

    Returns:
    (total_energy_joules, mean_voltage_v, mean_current_ma, mean_power_mw)
    """
    n = len(timestamps_ms)
    if n < 2 or len(voltage_v_samples) != n or len(current_ma_samples) != n:
        if n == 1:
            v = voltage_v_samples[0]
            i_ma = current_ma_samples[0]
            p_mw = v * i_ma
            return 0.0, round(v, 4), round(i_ma, 4), round(p_mw, 4)
        return 0.0, 0.0, 0.0, 0.0

    total_joules = 0.0
    for k in range(n - 1):
        dt_s = (timestamps_ms[k + 1] - timestamps_ms[k]) / 1000.0
        if dt_s < 0:
            continue  # Ignore non-monotonic anomaly

        # Instantaneous power in Watts: V * (mA / 1000)
        p1_w = voltage_v_samples[k] * (current_ma_samples[k] / 1000.0)
        p2_w = voltage_v_samples[k + 1] * (current_ma_samples[k + 1] / 1000.0)

        # Trapezoidal rule slice
        slice_joules = 0.5 * (p1_w + p2_w) * dt_s
        total_joules += slice_joules

    mean_v = sum(voltage_v_samples) / n
    mean_i_ma = sum(current_ma_samples) / n
    mean_p_mw = sum(v * i for v, i in zip(voltage_v_samples, current_ma_samples)) / n

    return (
        round(total_joules, 6),
        round(mean_v, 4),
        round(mean_i_ma, 4),
        round(mean_p_mw, 4),
    )


def compute_indicative_runtime_hours(
    battery_nominal_mah: float,
    usable_factor: float,
    mean_current_ma: float,
) -> Optional[float]:
    """Calculate indicative battery runtime:
    Runtime (hours) = (nominal_mah * usable_factor) / mean_current_ma

    CAUTION: This is an indicative software estimate affected by chemistry,
    regulator efficiency, temperature, and duty cycles.
    """
    if mean_current_ma <= 0 or battery_nominal_mah <= 0 or usable_factor <= 0:
        return None
    usable_capacity_mah = battery_nominal_mah * usable_factor
    hours = usable_capacity_mah / mean_current_ma
    return round(hours, 2)


def compute_charge_consumed_mah(
    mean_current_ma: float,
    duration_s: float,
) -> float:
    """Calculate estimated battery charge consumed in mAh:
    Charge (mAh) = mean_current_ma * (duration_s / 3600.0)
    """
    if mean_current_ma <= 0 or duration_s <= 0:
        return 0.0
    hours = duration_s / 3600.0
    return round(mean_current_ma * hours, 6)


def compute_authoritative_comparison(
    baseline_val: float,
    proposed_val: float,
    metric_name: str,
    lower_is_better: bool = True,
    is_energy_metric: bool = False,
) -> Dict[str, Any]:
    """Authoritative comparison calculation engine used by API, dashboard, and exports.
    Calculates percentage change and energy savings from unrounded raw values.
    """
    pct_change = calculate_percentage_change(baseline_val, proposed_val)
    abs_diff = proposed_val - baseline_val
    status = evaluate_result_status(baseline_val, proposed_val, lower_is_better=lower_is_better)
    is_improvement = (status == "IMPROVEMENT")

    res: Dict[str, Any] = {
        "metric_name": metric_name,
        "baseline": baseline_val,
        "proposed": proposed_val,
        "absolute_diff": abs_diff,
        "percentage_change": pct_change,
        "percent_change": pct_change,
        "result_status": status,
        "is_improvement": is_improvement,
    }

    if is_energy_metric:
        saving_pct = calculate_energy_saving(baseline_val, proposed_val)
        res["energy_saving_percent"] = saving_pct
        if saving_pct > 0.2:
            direction_str = f"SAVING ({saving_pct:+.2f}%)"
            explanation_str = f"Proposed approach saved {abs(saving_pct):.2f}% energy relative to baseline."
        elif saving_pct < -0.2:
            direction_str = f"EXTRA CONSUMPTION ({abs(saving_pct):.2f}%)"
            explanation_str = f"Proposed approach consumed {abs(saving_pct):.2f}% more energy than baseline (regression)."
        else:
            direction_str = "INCONCLUSIVE (Within noise margin)"
            explanation_str = "Energy consumption was identical within noise threshold."
    else:
        if lower_is_better:
            if pct_change < -0.2:
                direction_str = "REDUCED (BETTER)"
                explanation_str = f"Latency reduced by {abs(pct_change):.2f}% relative to baseline."
            elif pct_change > 0.2:
                direction_str = "INCREASED (WORSE) - INCREASED (WORSE / REGRESSION)"
                explanation_str = f"Latency increased by {abs(pct_change):.2f}% relative to baseline (regression)."
            else:
                direction_str = "INCONCLUSIVE"
                explanation_str = "Measured latency was identical within noise threshold."
        else:
            if pct_change > 0.2:
                direction_str = "INCREASED (BETTER)"
                explanation_str = f"Transmission success increased by {abs(pct_change):.2f}%."
            elif pct_change < -0.2:
                direction_str = "DECREASED (WORSE) - DECREASED (WORSE / REGRESSION)"
                explanation_str = f"Transmission success decreased by {abs(pct_change):.2f}%."
            else:
                direction_str = "INCONCLUSIVE"
                explanation_str = "Delivery rates identical."

    res["direction"] = direction_str
    res["explanation"] = explanation_str

    # Formatted display convenience fields
    res["baseline_display"] = round(baseline_val, 6)
    res["proposed_display"] = round(proposed_val, 6)
    res["absolute_diff_display"] = round(abs_diff, 6)
    res["percent_change_display"] = round(pct_change, 2)

    return res


def compute_percentage_change(
    baseline_val: float,
    adaptive_val: float,
    lower_is_better: bool = True,
) -> Dict[str, Any]:
    """Compatibility wrapper redirecting to authoritative comparison engine."""
    is_energy = "energy" in "unknown"
    return compute_authoritative_comparison(
        baseline_val=baseline_val,
        proposed_val=adaptive_val,
        metric_name="value",
        lower_is_better=lower_is_better,
        is_energy_metric=is_energy,
    )
