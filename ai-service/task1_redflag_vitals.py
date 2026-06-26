"""
Task 1: Red-Flag Vitals Rules Engine
=====================================
Scans a patient's vital readings and flags abnormal values based on
standard clinical reference ranges.

WHY NO AI MODEL HERE?
Clinical reference ranges are well-defined and deterministic.
An LLM would just guess and could be wrong in dangerous ways.
A rules engine is faster, free, auditable, and clinically defensible.

You can later wrap this in an API endpoint that the doctor's UI calls.

HOW TO RUN:
  1. First run generate_synthetic_data.py to create output/vital_details.json
  2. Then run:  python task1_redflag_vitals.py
  3. Output: flag_report.json with all abnormal patients & their flags
  4. Also prints a summary to terminal

YOU CAN ALSO IMPORT THIS:
  from task1_redflag_vitals import analyze_vitals
  flags = analyze_vitals(vital_record)  # returns list of flags
"""

import json
import re
from pathlib import Path

# =========================
# CLINICAL REFERENCE RANGES (Adult)
# =========================
# Sources: WHO / American Heart Association / standard internal medicine references.
# For pediatric or geriatric patients, ranges should be adjusted.
# These are STARTING POINTS. Your clinical team should review & sign off.

THRESHOLDS = {
    "temperature_f": {
        "low_critical": 95.0,    # hypothermia
        "low_watch":   97.0,
        "high_watch":  99.5,     # low-grade fever
        "high":        100.4,    # fever (CDC threshold)
        "high_critical": 103.0,  # high fever
    },
    "systolic_bp": {
        "low_critical": 80,
        "low_watch":    90,
        "high_watch":   130,     # Stage 1 HTN per AHA 2017
        "high":         140,     # Stage 2 HTN
        "high_critical": 180,    # Hypertensive crisis
    },
    "diastolic_bp": {
        "low_critical": 50,
        "low_watch":    60,
        "high_watch":   80,
        "high":         90,
        "high_critical": 120,
    },
    "spo2_pct": {
        "low_critical": 89.999,  # severe hypoxia (<90% per clinical convention)
        "low_watch":    94.999,  # mild hypoxia (<95%)
        # No high abnormal for SpO2
    },
    "blood_glucose_mgdl": {
        "low_critical": 54,      # severe hypoglycemia
        "low_watch":    70,
        "high_watch":   140,     # post-meal upper
        "high":         200,
        "high_critical": 300,
    },
    "weight_kg": {
        # Weight alone isn't a red flag — need BMI. Flag only extreme outliers.
        "low_critical": 35,
        "high_critical": 150,
    },
}

SEVERITY_ORDER = {"NORMAL": 0, "WATCH": 1, "HIGH": 2, "CRITICAL": 3}

# =========================
# PARSERS
# =========================
# Vitals are stored as strings per schema. Need careful parsing.

def parse_number(s):
    """Extract the first number from a string. '98.6 F' -> 98.6, '75 kg' -> 75.0"""
    if s is None:
        return None
    match = re.search(r"-?\d+\.?\d*", str(s))
    return float(match.group()) if match else None

def parse_bp(s):
    """Parse '120/80' -> (120, 80). Returns (None, None) if it can't parse."""
    if not s:
        return (None, None)
    match = re.match(r"\s*(\d+)\s*/\s*(\d+)", str(s))
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return (None, None)

def parse_temp_to_f(s):
    """Parse temperature string and return Fahrenheit value.
    Accepts: '98.6 F', '98.6F', '37.0 C', '37C', '98.6'  (assumes F if no unit)"""
    if not s:
        return None
    val = parse_number(s)
    if val is None:
        return None
    s_upper = str(s).upper()
    if "C" in s_upper and "F" not in s_upper:
        return val * 9 / 5 + 32  # convert C to F
    return val

# =========================
# EPISODE ADAPTER
# =========================
# generate_synthetic_data.py now stores each visit as a multi-hour monitoring
# episode (vitals sampled repeatedly on their own intervals, under
# vitals[i].readings.<vital>.samples) rather than one reading per visit. This
# rules engine scores a single snapshot, so we adapt an episode down to its
# latest known-good reading per vital before scoring -- the scoring logic
# itself is unchanged and still works on a plain single-reading dict (e.g.
# live data from a paramedic's one-off manual entry).

def _latest_good_value(readings, vital):
    """Last non-garbled sample for a vital channel, falling back to the last
    sample of any quality if every reading was garbled."""
    samples = (readings.get(vital) or {}).get("samples", [])
    good = [s for s in samples if s.get("quality") != "garbled"]
    chosen = (good or samples)
    if not chosen:
        return None, None
    last = chosen[-1]
    return last.get("value"), last.get("timestamp")

def _flatten_episode(vital_entry):
    """If vital_entry is a monitoring episode (has 'readings'), reduce it to a
    flat {weight, temperature, blood_pressure, blood_oxygen, blood_glucose,
    createdAt} snapshot of its latest readings. Already-flat entries (legacy
    single-reading shape) pass through unchanged."""
    readings = vital_entry.get("readings")
    if not readings:
        return vital_entry

    flat = {"weight": vital_entry.get("weight")}
    last_ts = vital_entry.get("updatedAt") or vital_entry.get("episode_end")
    for vital in ("temperature", "blood_oxygen", "blood_glucose", "blood_pressure"):
        value, ts = _latest_good_value(readings, vital)
        flat[vital] = value
        if ts:
            last_ts = ts
    flat["createdAt"] = last_ts
    return flat

# =========================
# CLASSIFIERS
# =========================

def classify(value, key, direction="bidirectional"):
    """
    Given a numeric value and a threshold key, return a severity label.
    direction: 'bidirectional' | 'high_only' | 'low_only'
    """
    if value is None:
        return None
    t = THRESHOLDS[key]
    severity = "NORMAL"

    if direction in ("bidirectional", "high_only"):
        if "high_critical" in t and value >= t["high_critical"]:
            return "CRITICAL"
        if "high" in t and value >= t["high"]:
            severity = "HIGH"
        elif "high_watch" in t and value >= t["high_watch"]:
            severity = "WATCH"

    if direction in ("bidirectional", "low_only") and severity == "NORMAL":
        if "low_critical" in t and value <= t["low_critical"]:
            return "CRITICAL"
        if "low_watch" in t and value <= t["low_watch"]:
            severity = "WATCH"

    return severity

# =========================
# MAIN ANALYZER
# =========================

# =========================
# NEWS2-INDIA SCORING ENGINE
# =========================
# National Early Warning Score 2 (Royal College of Physicians), adapted for
# Indian use. This dataset only carries 3 of the 7 NEWS2 parameters
# (SpO2, systolic BP, temperature), so this is a PARTIAL NEWS2 — the missing
# parameters (respiratory rate, heart rate, consciousness/AVPU, supplemental
# oxygen) are reported as unavailable and excluded from the total.
#
# Indian adaptation notes:
#   - Temperature fever threshold uses 37.9 C (not 38.0 C).
#   - SpO2 Scale 2 (for COPD/asthma target range 88-92%) is supported via the
#     scale2 flag; default is Scale 1.
NEWS2_VERSION = "indian_adaptation_v1_partial"

# Parameters we cannot score from this dataset.
NEWS2_MISSING_PARAMS = ["respiratory_rate", "heart_rate", "consciousness", "supplemental_oxygen"]


def _score_spo2_scale1(spo2):
    """NEWS2 Scale 1 SpO2 sub-score (most patients)."""
    if spo2 is None:
        return None
    if spo2 <= 91:
        return 3
    if spo2 <= 93:
        return 2
    if spo2 <= 95:
        return 1
    return 0


def _score_spo2_scale2(spo2):
    """NEWS2 Scale 2 SpO2 sub-score (COPD/asthma, target 88-92%)."""
    if spo2 is None:
        return None
    if spo2 <= 83:
        return 3
    if spo2 <= 85:
        return 2
    if spo2 <= 87:
        return 1
    if spo2 <= 92:
        return 0
    if spo2 <= 94:
        return 1
    if spo2 <= 96:
        return 2
    return 3


def _score_systolic(sbp):
    """NEWS2 systolic BP sub-score."""
    if sbp is None:
        return None
    if sbp <= 90:
        return 3
    if sbp <= 100:
        return 2
    if sbp <= 110:
        return 1
    if sbp <= 219:
        return 0
    return 3  # >=220


def _score_temp_india(temp_f):
    """NEWS2 temperature sub-score, Indian threshold (37.9 C). Input is Fahrenheit."""
    if temp_f is None:
        return None
    temp_c = (temp_f - 32) * 5 / 9
    if temp_c <= 35.0:
        return 3
    if temp_c <= 36.0:
        return 1
    if temp_c <= 37.9:   # India: fever starts above 37.9 (not 38.0)
        return 0
    if temp_c <= 39.0:
        return 1
    return 2  # >39.0


def _news2_risk(total, any_param_is_3):
    """Map a NEWS2 total to a risk band. A single 3 in any one parameter is
    at least medium risk regardless of total."""
    if total >= 7:
        return "CRITICAL"
    if total >= 5 or any_param_is_3:
        return "HIGH"
    if total >= 1:
        return "WATCH"
    return "NORMAL"


def analyze_vitals(vital_entry, spo2_scale2=False):
    """
    NEWS2-India scoring of a SINGLE vitals reading.
    Returns a dict (NOT a list — this differs from the old rules engine) with
    the total score, risk band, per-parameter sub-scores, flags, and a note
    about which parameters were unavailable.
    """
    vital_entry = _flatten_episode(vital_entry)
    reading_date = vital_entry.get("createdAt", "")

    spo2 = parse_number(vital_entry.get("blood_oxygen"))
    sys_bp, _dia = parse_bp(vital_entry.get("blood_pressure"))
    temp_f = parse_temp_to_f(vital_entry.get("temperature"))

    sub = {}
    sub["spo2"] = _score_spo2_scale2(spo2) if spo2_scale2 else _score_spo2_scale1(spo2)
    sub["systolic_bp"] = _score_systolic(sys_bp)
    sub["temperature"] = _score_temp_india(temp_f)

    scored = {k: v for k, v in sub.items() if v is not None}
    total = sum(scored.values())
    any_three = any(v == 3 for v in scored.values())
    risk = _news2_risk(total, any_three)

    # Build human-readable flags for any parameter scoring >0
    flags = []
    labels = {
        "spo2": ("blood_oxygen", spo2, "%"),
        "systolic_bp": ("blood_pressure", sys_bp, " mmHg systolic"),
        "temperature": ("temperature", round((temp_f - 32) * 5 / 9, 1) if temp_f is not None else None, "°C"),
    }
    for key, score in scored.items():
        if score > 0:
            metric, value, unit = labels[key]
            sev = "CRITICAL" if score == 3 and (total >= 7) else ("HIGH" if score == 3 else ("WATCH" if score >= 1 else "NORMAL"))
            flags.append({
                "metric": metric,
                "news2_subscore": score,
                "value": f"{value}{unit}" if value is not None else "n/a",
                "severity": "HIGH" if score >= 2 else "WATCH",
                "reason": f"{metric.replace('_', ' ')} scores {score} on NEWS2 ({value}{unit})",
                "reading_date": reading_date,
            })

    return {
        "news2_version": NEWS2_VERSION,
        "news2_total": total,
        "spo2_scale_used": 2 if spo2_scale2 else 1,
        "subscores": {
            "n2_spo2": sub["spo2"],
            "n2_systolic_bp": sub["systolic_bp"],
            "n2_temperature": sub["temperature"],
        },
        "parameters_scored": list(scored.keys()),
        "parameters_unavailable": NEWS2_MISSING_PARAMS,
        "risk_level": risk,
        "flags": flags,
    }


def analyze_latest_visit(vital_details_doc, spo2_scale2=False):
    """
    NEWS2-India: score the patient's LATEST vitals entry.
    Keeps the same response keys the API/React expect (patient_id, vitals,
    overall_severity, flag_count, flags) and adds NEWS2 fields.
    """
    vitals_array = vital_details_doc.get("vitals", [])
    if not vitals_array:
        return {"patient_id": vital_details_doc.get("patient_id"), "flags": [], "status": "no_vitals"}

    latest = _flatten_episode(vitals_array[-1])
    result = analyze_vitals(latest, spo2_scale2=spo2_scale2)

    return {
        "patient_id": vital_details_doc.get("patient_id"),
        "reading_date": latest.get("createdAt"),
        "vitals": {
            "weight": latest.get("weight"),
            "temperature": latest.get("temperature"),
            "blood_pressure": latest.get("blood_pressure"),
            "blood_oxygen": latest.get("blood_oxygen"),
            "blood_glucose": latest.get("blood_glucose"),
        },
        # NEWS2 fields
        "scoring_system": "NEWS2-India (partial — 3 of 7 parameters)",
        "news2_version": result["news2_version"],
        "news2_total": result["news2_total"],
        "spo2_scale_used": result["spo2_scale_used"],
        "subscores": result["subscores"],
        "parameters_scored": result["parameters_scored"],
        "parameters_unavailable": result["parameters_unavailable"],
        # keep old keys so the existing UI keeps working
        "overall_severity": result["risk_level"],
        "flag_count": len(result["flags"]),
        "flags": result["flags"],
    }


# =========================
# BATCH RUNNER
# =========================

def run_batch_analysis(input_file="output/vital_details.json", output_file="output/flag_report.json"):
    """Run NEWS2-India analysis on all patients in vital_details.json."""
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"ERROR: {input_path} not found. Run generate_synthetic_data.py first.")
        return

    with open(input_path) as f:
        vital_records = json.load(f)

    print(f"NEWS2-India scoring {len(vital_records)} patient vital records...")

    results = []
    summary = {"NORMAL": 0, "WATCH": 0, "HIGH": 0, "CRITICAL": 0, "no_vitals": 0}

    for record in vital_records:
        result = analyze_latest_visit(record)
        results.append(result)
        if result.get("status") == "no_vitals":
            summary["no_vitals"] += 1
        else:
            summary[result["overall_severity"]] += 1

    results.sort(key=lambda r: -r.get("news2_total", 0))

    output_path = Path(output_file)
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\n" + "=" * 60)
    print("NEWS2-INDIA ANALYSIS SUMMARY (partial: SpO2, BP, Temp)")
    print("=" * 60)
    print(f"  CRITICAL (>=7) : {summary['CRITICAL']:>4}  <-- emergency response")
    print(f"  HIGH (5-6/3)   : {summary['HIGH']:>4}")
    print(f"  WATCH (1-4)    : {summary['WATCH']:>4}")
    print(f"  NORMAL (0)     : {summary['NORMAL']:>4}")
    print(f"  No vitals      : {summary['no_vitals']:>4}")
    print("=" * 60)
    print(f"\nFull report written to: {output_path.absolute()}")
    return results


if __name__ == "__main__":
    run_batch_analysis()