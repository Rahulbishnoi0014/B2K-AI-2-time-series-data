"""
Task 5: ML Risk Classifier (trained on vitals trends)
========================================================
Trains a classifier to predict critical/normal from the RAW vitals trend of
a monitoring episode (per-vital mean/slope/variance/etc.), instead of from
one snapshot reading.

IMPORTANT — WHAT THE LABEL ACTUALLY IS:
This is synthetic data, so there are no real patient outcomes to learn from.
The label is Task 1's actual NEWS2-India score (task1_redflag_vitals.
analyze_vitals), computed on the episode's latest reading: 1 if risk_level
is HIGH or CRITICAL, 0 if WATCH/NORMAL. This is a deterministic clinical
formula, not ground truth -- so this script is NOT "rules vs ML on real
outcomes". It is: "can a model learn to approximate Task 1's NEWS2 rule
from raw trend features, without being given the rule's thresholds?" That is
still a legitimate, common technique (training a model against a clinical
score as a silver-standard label), and the interesting output is (a) how
well a learned model recovers the rule's structure, and (b) which trend
features it finds most predictive (model_feature_importances) -- which vital
behaviors actually drive risk, learned rather than hand-specified.

Note: generate_synthetic_data.py also computes its own composite
early_warning_score (5 vitals incl. glucose/spirometer, trajectory + trend
slope based). That is a richer simulation-time signal but is NOT NEWS2 and
is deliberately not used as the label here, so Task 5 stays comparable to
Task 1's actual NEWS2 output.

FEATURES (per episode, computed ONLY from raw readings, never from the
early_warning_score fields, to avoid leaking the label into the input):
  For temperature, blood_oxygen, blood_glucose, spirometer, and blood
  pressure (systolic + diastolic separately):
    n_readings, mean, std, min, max, first, last, delta (last-first),
    slope_per_hour, pct_garbled
  Plus: weight_kg, duration_hours

HOW TO RUN:
  1. Generate a LARGER dataset for training (the live demo set is small by
     design): from data-seed/, run generate_synthetic_data.py with
     NUM_PATIENTS_PER_TENANT bumped up and OUTPUT_DIR pointed at a separate
     folder (e.g. output_train/), so you don't disturb the demo data.
  2. python task5_ml_risk_classifier.py output_train/vital_details.json
     (defaults to ../data-seed/vital_details.json)
  3. Outputs: output_train/risk_classifier.joblib (the trained model) and
     output_train/risk_classifier_report.json (metrics + feature importances)
"""

import json
import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, f1_score
import joblib

from task1_redflag_vitals import analyze_vitals

VITAL_CHANNELS = ["temperature", "blood_oxygen", "blood_glucose", "spirometer"]

# Fixed deploy location ai_api.py's predict_episode() loads from by default.
# Resolved relative to this file (not cwd) so training and serving always
# agree on the path regardless of where each process was launched from.
DEPLOY_MODEL_PATH = Path(__file__).resolve().parent / "models" / "risk_classifier.joblib"


def parse_num(s):
    import re
    if s is None:
        return None
    m = re.search(r"-?\d+\.?\d*", str(s))
    return float(m.group()) if m else None


def parse_bp(s):
    import re
    m = re.match(r"\s*(\d+)\s*/\s*(\d+)", str(s or ""))
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def channel_stats(samples, prefix, extractor):
    """Compute the 10 trend features for one vital's samples list."""
    good = [(s["timestamp"], extractor(s["value"])) for s in samples if s.get("quality") != "garbled"]
    good = [(t, v) for t, v in good if v is not None]
    n_total = len(samples) or 1
    n_garbled = sum(1 for s in samples if s.get("quality") == "garbled")
    feats = {f"{prefix}_pct_garbled": n_garbled / n_total}

    if len(good) < 2:
        for name in ("n_readings", "mean", "std", "min", "max", "first", "last", "delta", "slope_per_hour"):
            feats[f"{prefix}_{name}"] = 0.0
        return feats

    values = np.array([v for _, v in good], dtype=float)
    hours = np.array([
        (np_datetime(t) - np_datetime(good[0][0])).total_seconds() / 3600 for t, _ in good
    ])
    slope = np.polyfit(hours, values, 1)[0] if np.ptp(hours) > 0 else 0.0

    feats[f"{prefix}_n_readings"] = float(len(good))
    feats[f"{prefix}_mean"] = float(values.mean())
    feats[f"{prefix}_std"] = float(values.std())
    feats[f"{prefix}_min"] = float(values.min())
    feats[f"{prefix}_max"] = float(values.max())
    feats[f"{prefix}_first"] = float(values[0])
    feats[f"{prefix}_last"] = float(values[-1])
    feats[f"{prefix}_delta"] = float(values[-1] - values[0])
    feats[f"{prefix}_slope_per_hour"] = float(slope)
    return feats


def np_datetime(iso_str):
    from datetime import datetime
    return datetime.fromisoformat(iso_str)


def extract_features(episode):
    """Build the flat feature dict for one monitoring episode, from raw
    readings only -- never touches early_warning_score (that's the label)."""
    readings = episode.get("readings", {})
    feats = {}

    for vital in VITAL_CHANNELS:
        samples = (readings.get(vital) or {}).get("samples", [])
        feats.update(channel_stats(samples, vital, parse_num))

    bp_samples = (readings.get("blood_pressure") or {}).get("samples", [])
    feats.update(channel_stats(bp_samples, "bp_systolic", lambda v: parse_bp(v)[0]))
    feats.update(channel_stats(bp_samples, "bp_diastolic", lambda v: parse_bp(v)[1]))

    feats["weight_kg"] = parse_num(episode.get("weight")) or 0.0
    feats["duration_hours"] = float(episode.get("duration_hours") or 0)
    return feats


def build_dataset(vital_details_path):
    with open(vital_details_path) as f:
        records = json.load(f)

    rows, labels, meta = [], [], []
    for rec in records:
        for ep in rec.get("vitals", []):
            if not ep.get("readings"):
                continue  # legacy single-reading shape, no episode to learn from
            news2 = analyze_vitals(ep)
            label = 1 if news2["risk_level"] in ("HIGH", "CRITICAL") else 0
            rows.append(extract_features(ep))
            labels.append(label)
            meta.append({"patient_id": rec.get("patient_id"), "risk_level": news2["risk_level"]})

    feature_names = sorted(rows[0].keys())
    X = np.array([[r[k] for k in feature_names] for r in rows])
    y = np.array(labels)
    return X, y, feature_names, meta


def train_and_evaluate(vital_details_path, output_dir):
    print(f"Loading episodes from {vital_details_path} ...")
    X, y, feature_names, meta = build_dataset(vital_details_path)
    print(f"  {len(y)} episodes, {y.sum()} critical ({100 * y.mean():.1f}%), {len(feature_names)} features")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=200, max_depth=8, class_weight="balanced", random_state=42
    )
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)

    acc = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, target_names=["normal", "critical"], output_dict=True)
    cm = confusion_matrix(y_test, y_pred).tolist()

    importances = sorted(
        zip(feature_names, clf.feature_importances_.tolist()), key=lambda kv: -kv[1]
    )

    print("\n" + "=" * 60)
    print("TASK 5: ML RISK CLASSIFIER — EVALUATION (held-out test set)")
    print("=" * 60)
    print(f"  Test set size : {len(y_test)} episodes")
    print(f"  Accuracy      : {acc:.3f}")
    print(f"  F1 (critical) : {f1:.3f}")
    print(f"  Confusion matrix [ [TN, FP], [FN, TP] ]: {cm}")
    print("\n  Top 10 predictive features:")
    for name, score in importances[:10]:
        print(f"    {name:<28} {score:.4f}")
    print("=" * 60)

    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    bundle = {"model": clf, "feature_names": feature_names}
    joblib.dump(bundle, output_dir / "risk_classifier.joblib")

    # Auto-deploy: also drop a copy where the live API loads from, so
    # retraining never requires a manual copy step.
    DEPLOY_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, DEPLOY_MODEL_PATH)
    _MODEL_CACHE.pop(str(DEPLOY_MODEL_PATH), None)  # invalidate any cached in-process model

    report_path = output_dir / "risk_classifier_report.json"
    with open(report_path, "w") as f:
        json.dump({
            "n_episodes": len(y),
            "n_critical": int(y.sum()),
            "test_accuracy": acc,
            "test_f1_critical": f1,
            "classification_report": report,
            "confusion_matrix": cm,
            "feature_importances": importances,
        }, f, indent=2)

    print(f"\nModel saved to:  {output_dir / 'risk_classifier.joblib'}")
    print(f"Deployed to:     {DEPLOY_MODEL_PATH}  (ai_api.py loads from here automatically)")
    print(f"Report saved to: {report_path}")
    return clf, feature_names


# =========================
# LIVE INFERENCE (used by ai_api.py)
# =========================

_MODEL_CACHE = {}

def load_model(model_path=None):
    """Load the trained classifier once and cache it in-process."""
    model_path = str(model_path or DEPLOY_MODEL_PATH)
    if model_path not in _MODEL_CACHE:
        bundle = joblib.load(model_path)
        _MODEL_CACHE[model_path] = (bundle["model"], bundle["feature_names"])
    return _MODEL_CACHE[model_path]


def predict_episode(episode, model_path=None):
    """
    Score one monitoring episode with the trained classifier. Reuses
    extract_features() so inference sees EXACTLY the same feature
    computation the model was trained on.
    """
    clf, feature_names = load_model(model_path)
    feats = extract_features(episode)
    x = np.array([[feats.get(name, 0.0) for name in feature_names]])
    proba_critical = float(clf.predict_proba(x)[0][1])
    return {
        "ml_is_critical": bool(proba_critical >= 0.5),
        "ml_risk_probability": round(proba_critical, 4),
        "model": "RandomForestClassifier (task5_ml_risk_classifier)",
    }


if __name__ == "__main__":
    default_path = Path("./output/vital_details.json")
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path
    if not path.exists():
        print(f"ERROR: {path} not found. Generate a (larger) training dataset first.")
        raise SystemExit(1)
    train_and_evaluate(path, path.parent)
