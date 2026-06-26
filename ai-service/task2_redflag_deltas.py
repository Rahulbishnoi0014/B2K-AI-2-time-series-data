"""
Task 2: Cross-Visit Vitals Delta Detection
============================================
Compares a patient's CURRENT visit vitals against their PREVIOUS visit
and flags significant changes. Runs alongside Task 1 — Task 1 catches
absolute abnormalities, Task 2 catches concerning trends.

WHY NO LLM HERE?
Same reason as Task 1: deltas are deterministic. An LLM would guess.

EXAMPLES OF WHAT THIS CATCHES (that Task 1 might miss):
- BP went from 118/76 to 138/88 — both could be "borderline" individually,
  but a 20-point systolic jump in days is clinically significant.
- SpO2 dropped from 98% to 94% — both technically "normal-ish",
  but the drop itself is the warning.
- Weight dropped 8 kg in 2 months — neither weight is abnormal alone,
  but the change is.

HOW TO RUN:
  1. Run generate_synthetic_data.py first
  2. Run task1_redflag_vitals.py (optional, but useful for comparison)
  3. Run: python task2_redflag_deltas.py
  4. Output: output/delta_report.json
"""

import json
import re
from datetime import datetime
from pathlib import Path

# Import the parsers from Task 1 so we don't duplicate code
from task1_redflag_vitals import parse_number, parse_bp, parse_temp_to_f, SEVERITY_ORDER, _flatten_episode

# =========================
# DELTA THRESHOLDS
# =========================
# These define what counts as a "significant change" between visits.
# Like Task 1 thresholds, these should be reviewed by your clinical team.

DELTA_THRESHOLDS = {
    "systolic_bp": {
        "watch":    15,   # +/- 15 mmHg systolic change
        "high":     25,
        "critical": 40,
    },
    "diastolic_bp": {
        "watch":    10,
        "high":     15,
        "critical": 25,
    },
    "spo2_pct": {
        "watch":    -3,    # dropped 3 percentage points
        "high":     -5,
        "critical": -8,
    },
    "blood_glucose_mgdl": {
        "watch":    50,    # ±50 mg/dL
        "high":     100,
        "critical": 150,
    },
    "temperature_f": {
        "watch":    1.5,
        "high":     2.5,
        "critical": 4.0,
    },
    "weight_kg_percent": {  # As a % of body weight
        "watch":    5,     # 5% change in body weight
        "high":     8,
        "critical": 12,
    },
}

# Time windows over which deltas matter most. A 5kg weight change in 7 days
# is more alarming than 5kg over a year.
RAPID_CHANGE_DAYS = 30  # Anything inside this window gets escalated severity


# =========================
# DELTA CALCULATIONS
# =========================

def classify_delta(delta_value, key, lower_is_worse=False):
    """
    Given a numeric delta and a threshold key, return severity.
    If lower_is_worse=True (e.g. SpO2 drop), negative deltas are bad.
    Otherwise, the absolute value determines severity.
    """
    if delta_value is None:
        return "NORMAL"
    t = DELTA_THRESHOLDS[key]

    if lower_is_worse:
        # We care about drops (negative deltas)
        if delta_value <= t["critical"]:
            return "CRITICAL"
        if delta_value <= t["high"]:
            return "HIGH"
        if delta_value <= t["watch"]:
            return "WATCH"
        return "NORMAL"
    else:
        # Bidirectional — large change either way is concerning
        abs_d = abs(delta_value)
        if abs_d >= t["critical"]:
            return "CRITICAL"
        if abs_d >= t["high"]:
            return "HIGH"
        if abs_d >= t["watch"]:
            return "WATCH"
        return "NORMAL"


def days_between(date_str_a, date_str_b):
    """Calculate days between two ISO datetime strings. Returns None if parse fails."""
    try:
        d_a = datetime.fromisoformat(str(date_str_a).replace("Z", ""))
        d_b = datetime.fromisoformat(str(date_str_b).replace("Z", ""))
        return abs((d_b - d_a).days)
    except (ValueError, TypeError):
        return None


def escalate_if_rapid(severity, days_apart):
    """If a change happened in a short time window, bump severity up one level."""
    if days_apart is not None and days_apart <= RAPID_CHANGE_DAYS and severity in ("WATCH", "HIGH"):
        next_level = {"WATCH": "HIGH", "HIGH": "CRITICAL"}
        return next_level.get(severity, severity)
    return severity


# =========================
# CORE COMPARISON
# =========================

def compare_visits(current_vitals, previous_vitals):
    """
    Compare current visit vitals with previous visit vitals.
    Returns a list of delta-based flags.
    """
    flags = []

    current_date = current_vitals.get("createdAt", "")
    prev_date = previous_vitals.get("createdAt", "")
    days_apart = days_between(current_date, prev_date)

    # --- Blood Pressure ---
    cur_sys, cur_dia = parse_bp(current_vitals.get("blood_pressure"))
    prev_sys, prev_dia = parse_bp(previous_vitals.get("blood_pressure"))

    if all(v is not None for v in [cur_sys, cur_dia, prev_sys, prev_dia]):
        sys_delta = cur_sys - prev_sys
        dia_delta = cur_dia - prev_dia

        sys_sev = classify_delta(sys_delta, "systolic_bp")
        dia_sev = classify_delta(dia_delta, "diastolic_bp")
        worse_sev = max([sys_sev, dia_sev], key=lambda s: SEVERITY_ORDER[s])

        if worse_sev != "NORMAL":
            worse_sev = escalate_if_rapid(worse_sev, days_apart)
            direction = "rose" if sys_delta > 0 else "fell"
            flags.append({
                "metric": "blood_pressure_delta",
                "previous": f"{prev_sys}/{prev_dia}",
                "current": f"{cur_sys}/{cur_dia}",
                "delta": {"systolic": sys_delta, "diastolic": dia_delta},
                "days_apart": days_apart,
                "severity": worse_sev,
                "reason": (
                    f"BP {direction} from {prev_sys}/{prev_dia} to {cur_sys}/{cur_dia} "
                    f"({'+' if sys_delta >= 0 else ''}{sys_delta} systolic, "
                    f"{'+' if dia_delta >= 0 else ''}{dia_delta} diastolic) "
                    f"over {days_apart} days"
                    if days_apart is not None
                    else f"BP {direction} from {prev_sys}/{prev_dia} to {cur_sys}/{cur_dia}"
                ),
            })

    # --- SpO2 (lower is worse) ---
    cur_spo2 = parse_number(current_vitals.get("blood_oxygen"))
    prev_spo2 = parse_number(previous_vitals.get("blood_oxygen"))

    if cur_spo2 is not None and prev_spo2 is not None:
        delta = cur_spo2 - prev_spo2
        sev = classify_delta(delta, "spo2_pct", lower_is_worse=True)
        if sev != "NORMAL":
            sev = escalate_if_rapid(sev, days_apart)
            flags.append({
                "metric": "blood_oxygen_delta",
                "previous": f"{prev_spo2}%",
                "current": f"{cur_spo2}%",
                "delta": delta,
                "days_apart": days_apart,
                "severity": sev,
                "reason": (
                    f"SpO2 dropped from {prev_spo2}% to {cur_spo2}% "
                    f"({delta:+.0f} points) over {days_apart} days"
                    if days_apart is not None
                    else f"SpO2 dropped from {prev_spo2}% to {cur_spo2}%"
                ),
            })

    # --- Blood Glucose ---
    cur_glu = parse_number(current_vitals.get("blood_glucose"))
    prev_glu = parse_number(previous_vitals.get("blood_glucose"))

    if cur_glu is not None and prev_glu is not None:
        delta = cur_glu - prev_glu
        sev = classify_delta(delta, "blood_glucose_mgdl")
        if sev != "NORMAL":
            sev = escalate_if_rapid(sev, days_apart)
            direction = "rose" if delta > 0 else "fell"
            flags.append({
                "metric": "blood_glucose_delta",
                "previous": f"{prev_glu:.0f} mg/dL",
                "current": f"{cur_glu:.0f} mg/dL",
                "delta": round(delta, 0),
                "days_apart": days_apart,
                "severity": sev,
                "reason": (
                    f"Blood glucose {direction} from {prev_glu:.0f} to {cur_glu:.0f} mg/dL "
                    f"({'+' if delta >= 0 else ''}{delta:.0f} mg/dL) over {days_apart} days"
                    if days_apart is not None
                    else f"Blood glucose {direction} from {prev_glu:.0f} to {cur_glu:.0f} mg/dL"
                ),
            })

    # --- Temperature ---
    cur_temp = parse_temp_to_f(current_vitals.get("temperature"))
    prev_temp = parse_temp_to_f(previous_vitals.get("temperature"))

    if cur_temp is not None and prev_temp is not None:
        delta = cur_temp - prev_temp
        sev = classify_delta(delta, "temperature_f")
        if sev != "NORMAL":
            sev = escalate_if_rapid(sev, days_apart)
            flags.append({
                "metric": "temperature_delta",
                "previous": f"{prev_temp:.1f} F",
                "current": f"{cur_temp:.1f} F",
                "delta": round(delta, 1),
                "days_apart": days_apart,
                "severity": sev,
                "reason": (
                    f"Temperature changed from {prev_temp:.1f}°F to {cur_temp:.1f}°F "
                    f"({delta:+.1f}°F) over {days_apart} days"
                    if days_apart is not None
                    else f"Temperature changed from {prev_temp:.1f}°F to {cur_temp:.1f}°F"
                ),
            })

    # --- Weight (as % change) ---
    cur_wt = parse_number(current_vitals.get("weight"))
    prev_wt = parse_number(previous_vitals.get("weight"))

    if cur_wt is not None and prev_wt is not None and prev_wt > 0:
        pct_change = ((cur_wt - prev_wt) / prev_wt) * 100
        sev = classify_delta(pct_change, "weight_kg_percent")
        if sev != "NORMAL":
            sev = escalate_if_rapid(sev, days_apart)
            direction = "gained" if pct_change > 0 else "lost"
            flags.append({
                "metric": "weight_delta",
                "previous": f"{prev_wt:.0f} kg",
                "current": f"{cur_wt:.0f} kg",
                "delta_kg": round(cur_wt - prev_wt, 1),
                "delta_pct": round(pct_change, 1),
                "days_apart": days_apart,
                "severity": sev,
                "reason": (
                    f"Patient {direction} {abs(cur_wt - prev_wt):.0f} kg "
                    f"({abs(pct_change):.1f}% of body weight) over {days_apart} days"
                    if days_apart is not None
                    else f"Patient {direction} {abs(cur_wt - prev_wt):.0f} kg ({abs(pct_change):.1f}% of body weight)"
                ),
            })

    return flags


def analyze_patient_deltas(vital_details_doc):
    """
    For a patient's VitalDetails document, compare the latest visit vs the previous one.
    Returns a dict with delta flags or a 'status' field if comparison isn't possible.
    """
    vitals_array = vital_details_doc.get("vitals", [])

    if len(vitals_array) == 0:
        return {
            "patient_id": vital_details_doc.get("patient_id"),
            "status": "no_vitals",
            "flags": [],
        }
    if len(vitals_array) == 1:
        return {
            "patient_id": vital_details_doc.get("patient_id"),
            "status": "single_visit_no_comparison",
            "flags": [],
        }

    # Vitals array is chronological — last = current, second-to-last = previous
    current = _flatten_episode(vitals_array[-1])
    previous = _flatten_episode(vitals_array[-2])

    flags = compare_visits(current, previous)
    overall_severity = "NORMAL"
    if flags:
        overall_severity = max(flags, key=lambda f: SEVERITY_ORDER[f["severity"]])["severity"]

    return {
        "patient_id": vital_details_doc.get("patient_id"),
        "status": "compared",
        "current_visit_date": current.get("createdAt"),
        "previous_visit_date": previous.get("createdAt"),
        "days_between_visits": days_between(current.get("createdAt"), previous.get("createdAt")),
        "overall_severity": overall_severity,
        "flag_count": len(flags),
        "flags": flags,
    }


# =========================
# BATCH RUNNER
# =========================

def run_batch_analysis(input_file="output/vital_details.json", output_file="output/delta_report.json"):
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"ERROR: {input_path} not found. Run generate_synthetic_data.py first.")
        return

    with open(input_path) as f:
        vital_records = json.load(f)

    print(f"Analyzing deltas for {len(vital_records)} patients...")

    results = []
    summary = {"NORMAL": 0, "WATCH": 0, "HIGH": 0, "CRITICAL": 0,
               "single_visit_no_comparison": 0, "no_vitals": 0}

    for record in vital_records:
        result = analyze_patient_deltas(record)
        results.append(result)
        if result.get("status") in ("no_vitals", "single_visit_no_comparison"):
            summary[result["status"]] += 1
        else:
            summary[result["overall_severity"]] += 1

    # Sort: critical first
    results.sort(key=lambda r: -SEVERITY_ORDER.get(r.get("overall_severity", "NORMAL"), 0))

    output_path = Path(output_file)
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\n" + "=" * 60)
    print("DELTA ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"  CRITICAL changes        : {summary['CRITICAL']:>4}")
    print(f"  HIGH changes            : {summary['HIGH']:>4}")
    print(f"  WATCH changes           : {summary['WATCH']:>4}")
    print(f"  NORMAL (stable)         : {summary['NORMAL']:>4}")
    print(f"  Single visit only       : {summary['single_visit_no_comparison']:>4}")
    print(f"  No vitals               : {summary['no_vitals']:>4}")
    print("=" * 60)

    critical_cases = [r for r in results if r.get("overall_severity") == "CRITICAL"][:3]
    if critical_cases:
        print("\nSAMPLE CRITICAL DELTAS (first 3):")
        for c in critical_cases:
            print(f"\n  Patient: {c['patient_id']}")
            print(f"  Visits {c['days_between_visits']} days apart:")
            for f in c["flags"]:
                if f["severity"] == "CRITICAL":
                    print(f"    [{f['severity']}] {f['reason']}")

    print(f"\nFull report: {output_path.absolute()}")
    return results


if __name__ == "__main__":
    run_batch_analysis()
