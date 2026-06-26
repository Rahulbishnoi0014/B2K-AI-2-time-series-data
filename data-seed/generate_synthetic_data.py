"""
Synthetic Patient Data Generator
=================================
Generates realistic mock data for the tele-consultation platform schema.
Produces JSON files matching the schema in your Data Schema Reference.

WHAT THIS DOES:
- Creates 2 tenants (hospitals)
- Creates 5 kiosks across them
- Creates ~50 doctors, 20 paramedics, 10 front-desk users, and 500 patients
- For each patient: vitals, consultations, prescriptions, history
- ~70% normal patients, ~30% with abnormal vitals (for testing red-flag AI)
- Each visit's vitals are a multi-hour monitoring episode: every vital is
  sampled on its own interval (e.g. SpO2 every few minutes, temperature every
  30-60 min), and the episode is labeled critical/normal from a NEWS2-style
  composite early warning score computed over the trajectory -- see
  output/vital_details.json -> vitals[i].early_warning_score

HOW TO RUN:
  1. Install Python 3.11 or newer
  2. Open a terminal in the folder containing this file
  3. Run:  pip install faker pymongo
  4. Run:  python generate_synthetic_data.py
  5. Output appears in the ./output/ folder as JSON files
  6. (Optional) To load into MongoDB, set LOAD_TO_MONGO = True below

OUTPUT FILES:
  output/tenants.json
  output/kiosks.json
  output/places.json
  output/users.json           (doctors, patients, paramedics, front-desk)
  output/doctor_slots.json
  output/symptoms_master.json
  output/diagnosis_master.json
  output/consultations.json
  output/patient_details.json
  output/vital_details.json
  output/drugs.json
  output/past_medical_history.json
  output/past_surgery.json
  output/family_history.json
  output/personal_social_history.json
"""

import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

# Try to import Faker; fail gracefully with helpful message
try:
    from faker import Faker
except ImportError:
    print("ERROR: 'faker' library not installed.")
    print("Please run:  pip install faker")
    raise SystemExit(1)

# =========================
# CONFIG
# =========================
NUM_TENANTS = 2
NUM_KIOSKS_PER_TENANT = 3
NUM_DOCTORS_PER_TENANT = 25
NUM_PARAMEDICS_PER_TENANT = 10
NUM_FRONTDESK_PER_TENANT = 5
NUM_PATIENTS_PER_TENANT = 15  # each patient's vitals are now a full time series, so kept small
ABNORMAL_PATIENT_RATIO = 0.30  # 30% of patients will have abnormal vitals
PRESENT_SYMPTOMS_RATIO = 0.50  # 50% of patients have CURRENT symptoms uploaded by
                               # a paramedic/portal user. The rest show "No symptoms
                               # added" on the doctor dashboard. Set 1.0 for all.
CONSULTATIONS_PER_PATIENT_MIN = 1
CONSULTATIONS_PER_PATIENT_MAX = 5

# Each visit is now a monitoring episode lasting EPISODE_DURATION_*_HOURS, during
# which every vital is sampled on its own interval (minutes), e.g. SpO2 every
# few minutes, temperature every 30-60 min, BP/glucose less often.
EPISODE_DURATION_MIN_HOURS = 6
EPISODE_DURATION_MAX_HOURS = 24
VITAL_SAMPLING_INTERVALS_MINUTES = {
    "temperature": (30, 60),
    "blood_oxygen": (5, 15),
    "blood_pressure": (60, 120),
    "blood_glucose": (120, 240),
    "spirometer": (240, 360),
}

OUTPUT_DIR = Path("./output")
LOAD_TO_MONGO = False  # Set True after installing pymongo + having Mongo running
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "teleconsult_dummy"

# =========================
# SEED DATA (Medical content)
# =========================
SYMPTOM_LIST = [
    "Fever", "Headache", "Cough", "Sore throat", "Fatigue", "Nausea", "Vomiting",
    "Diarrhea", "Constipation", "Chest pain", "Shortness of breath", "Dizziness",
    "Abdominal pain", "Back pain", "Joint pain", "Rash", "Itching", "Loss of appetite",
    "Weight loss", "Weight gain", "Insomnia", "Anxiety", "Palpitations", "Sweating",
    "Chills", "Muscle ache", "Runny nose", "Nasal congestion", "Ear pain", "Eye pain",
    "Blurred vision", "Numbness", "Tingling", "Weakness", "Seizure",
]

DIAGNOSIS_LIST = [
    "Hypertension", "Type 2 Diabetes Mellitus", "Type 1 Diabetes Mellitus",
    "Bronchial Asthma", "COPD", "Coronary Artery Disease", "Hypothyroidism",
    "Hyperthyroidism", "Urinary Tract Infection", "Gastroenteritis", "Migraine",
    "Tension Headache", "Anemia", "Acute Bronchitis", "Pneumonia", "Tuberculosis",
    "Allergic Rhinitis", "Dermatitis", "Osteoarthritis", "Rheumatoid Arthritis",
    "Depression", "Anxiety Disorder", "GERD", "Peptic Ulcer Disease",
    "Chronic Kidney Disease", "Dengue Fever", "Malaria", "Typhoid", "Viral Fever",
]

DRUG_LIST = [
    ("Paracetamol", "500mg"), ("Amoxicillin", "500mg"), ("Azithromycin", "500mg"),
    ("Metformin", "500mg"), ("Atorvastatin", "10mg"), ("Amlodipine", "5mg"),
    ("Losartan", "50mg"), ("Telmisartan", "40mg"), ("Pantoprazole", "40mg"),
    ("Omeprazole", "20mg"), ("Salbutamol", "100mcg"), ("Budesonide", "200mcg"),
    ("Cetirizine", "10mg"), ("Levocetirizine", "5mg"), ("Ibuprofen", "400mg"),
    ("Diclofenac", "50mg"), ("Insulin Glargine", "10 units"), ("Levothyroxine", "50mcg"),
    ("Aspirin", "75mg"), ("Clopidogrel", "75mg"), ("Ciprofloxacin", "500mg"),
    ("ORS sachet", "1 sachet"), ("Multivitamin", "1 tab"), ("Iron + Folic Acid", "1 tab"),
]

TEST_LIST = [
    "Complete Blood Count", "Blood Sugar Fasting", "Blood Sugar Postprandial",
    "HbA1c", "Lipid Profile", "Liver Function Test", "Kidney Function Test",
    "Thyroid Function Test", "Urine Routine", "ECG", "Chest X-Ray", "Ultrasound Abdomen",
    "ECHO", "MRI Brain", "CT Scan Chest", "Dengue NS1", "Malaria Parasite", "Widal Test",
    "COVID RT-PCR", "Vitamin D", "Vitamin B12", "CRP", "ESR",
]

PAST_SURGERY_LIST = [
    "Appendectomy", "Cesarean Section", "Cholecystectomy", "Hernia Repair",
    "Cataract Surgery", "Knee Replacement", "Tonsillectomy", "Hysterectomy",
]

FAMILY_DISEASE_LIST = [
    "Diabetes", "Hypertension", "Heart Disease", "Cancer", "Stroke",
    "Asthma", "Thyroid Disorder", "Kidney Disease",
]

ROUTES_LIST = ["Oral", "IV", "IM", "Topical", "Inhalation", "Sublingual"]

fake = Faker("en_IN")  # Indian-locale faker for realistic Indian names/addresses

# =========================
# ID GENERATION HELPERS
# =========================
def make_object_id():
    """Generate a 24-char hex string that looks like a MongoDB ObjectId."""
    return "".join(random.choices("0123456789abcdef", k=24))

def make_iso_date(days_ago_max=365):
    """A random ISO datetime within the last N days."""
    days_ago = random.randint(0, days_ago_max)
    dt = datetime.now() - timedelta(days=days_ago,
                                    hours=random.randint(0, 23),
                                    minutes=random.randint(0, 59))
    return dt.isoformat()

def make_dob(min_age=1, max_age=85):
    age = random.randint(min_age, max_age)
    dob = datetime.now() - timedelta(days=age * 365 + random.randint(0, 364))
    return dob.strftime("%Y-%m-%d")

def make_present_symptoms(paramedic_ids):
    """
    Build the dedicated 'present_symptoms' field that lives on a patient record.
    This is the CURRENT visit's symptoms, uploaded by a paramedic/portal user.
    It is a single overwritable slot (NOT visit history). Empty dict means
    nothing was uploaded -> doctor dashboard shows "No symptoms added".
    """
    if random.random() >= PRESENT_SYMPTOMS_RATIO:
        return {}  # nothing uploaded yet
    chosen = random.sample(SYMPTOM_LIST, k=random.randint(1, 4))
    now = datetime.now().replace(
        hour=random.randint(7, 18), minute=random.randint(0, 59), second=0, microsecond=0
    ).isoformat()
    return {
        "symptoms": chosen,
        "note": random.choice([
            "", "Patient reports onset this morning.",
            "Worsening since last night.", "Sudden onset.", "Mild but persistent.",
        ]),
        "uploaded_by": random.choice(paramedic_ids) if paramedic_ids else None,
        "uploaded_by_role": "paramedic",
        "updatedAt": now,
    }


# =========================
# VITALS TIME-SERIES GENERATION
# =========================
# Each visit is a multi-hour monitoring episode. Every vital is sampled on its
# own clinically realistic interval rather than once. The episode's
# critical/normal label is NOT chosen up front -- it is computed from the
# generated trajectory via a NEWS2-inspired composite early warning score
# (EWS), so the label reflects the trend rather than a single reading.

VITAL_PROFILES = {
    "temperature": {
        "normal_range": (97.0, 99.0), "high_range": (100.4, 104.0), "low_range": (93.0, 96.5),
        "clip": (93.0, 107.0), "noise": 0.15, "directions": ["high", "low"],
        "fmt": lambda v: f"{round(v, 1)} F",
    },
    "blood_oxygen": {
        "normal_range": (96, 100), "low_range": (82, 93),
        "clip": (70, 100), "noise": 0.4, "directions": ["low"],
        "fmt": lambda v: f"{round(v)}%",
    },
    "blood_glucose": {
        "normal_range": (75, 135), "high_range": (220, 400), "low_range": (40, 60),
        "clip": (30, 500), "noise": 3.0, "directions": ["high", "low"],
        "fmt": lambda v: f"{round(v)}",
    },
    "spirometer": {
        "normal_range": (380, 600), "low_range": (150, 349),
        "clip": (100, 650), "noise": 8.0, "directions": ["low"],
        "fmt": lambda v: f"{round(v)} L/min",
    },
}
BP_PROFILES = {
    "systolic": {"normal_range": (105, 125), "high_range": (140, 200), "low_range": (80, 95),
                 "clip": (70, 220), "noise": 2.0},
    "diastolic": {"normal_range": (65, 82), "high_range": (90, 120), "low_range": (50, 60),
                  "clip": (40, 130), "noise": 1.5},
}

DEVICE_DROPOUT_PROB = 0.04       # chance an individual scheduled reading is missed
DEVICE_OUTAGE_PROB = 0.15        # chance the device has one multi-reading connectivity outage
DEVICE_OUTAGE_LEN_RANGE = (2, 6) # consecutive scheduled readings lost during an outage
DEVICE_GLITCH_PROB = 0.012       # chance a transmitted reading is a garbled sensor spike

def make_episode_timestamps(start_dt, duration_minutes, interval_minutes):
    """
    Clock-aligned schedule for a device sampling every interval_minutes, with
    simulated connectivity issues: one chance of a contiguous outage plus a
    small independent chance of isolated missed readings.
    """
    n_scheduled = max(1, int(duration_minutes // interval_minutes) + 1)
    outage_start, outage_end = -1, -1
    if n_scheduled > 4 and random.random() < DEVICE_OUTAGE_PROB:
        outage_len = random.randint(*DEVICE_OUTAGE_LEN_RANGE)
        outage_len = min(outage_len, n_scheduled - 1)
        outage_start = random.randint(0, n_scheduled - outage_len)
        outage_end = outage_start + outage_len

    timestamps = []
    for i in range(n_scheduled):
        if outage_start <= i < outage_end:
            continue
        if random.random() < DEVICE_DROPOUT_PROB:
            continue
        timestamps.append(start_dt + timedelta(minutes=i * interval_minutes))
    return timestamps or [start_dt]

def gen_trend_series(timestamps, profile, abnormal, direction=None, behavior=None):
    """
    Random-walk a vital's value across `timestamps`.
    Abnormal series pick a direction (high/low) and a behavior (worsening,
    recovering, fluctuating) unless given, and drift accordingly. Normal
    series stay near a healthy baseline with small noise. A small fraction of
    readings are flagged "garbled" (sensor glitch/motion artifact) and carry
    an out-of-trend spike value -- these are excluded from EWS scoring.
    """
    if abnormal:
        direction = direction or random.choice(profile["directions"])
        behavior = behavior or random.choices(
            ["worsening", "recovering", "fluctuating"], weights=[0.5, 0.3, 0.2]
        )[0]
        abnormal_range = profile["high_range"] if direction == "high" else profile["low_range"]
        normal_range = profile["normal_range"]
        if behavior == "recovering":
            start, target = random.uniform(*abnormal_range), random.uniform(*normal_range)
        elif behavior == "worsening":
            mild = (abnormal_range[0] + normal_range[1]) / 2 if direction == "high" \
                else (abnormal_range[1] + normal_range[0]) / 2
            start, target = mild, random.uniform(*abnormal_range)
        else:  # fluctuating around an abnormal level
            start = random.uniform(*abnormal_range)
            target = start
        noise_mult = 2.0 if behavior == "fluctuating" else 1.0
    else:
        start = target = random.uniform(*profile["normal_range"])
        noise_mult = 1.0

    total_minutes = max(1.0, (timestamps[-1] - timestamps[0]).total_seconds() / 60)
    drift_per_min = (target - start) / total_minutes

    values = [start]
    for prev_t, t in zip(timestamps, timestamps[1:]):
        dt_min = (t - prev_t).total_seconds() / 60
        nxt = values[-1] + drift_per_min * dt_min + random.gauss(0, profile["noise"] * noise_mult)
        values.append(min(profile["clip"][1], max(profile["clip"][0], nxt)))

    clip_span = profile["clip"][1] - profile["clip"][0]
    quality = []
    for idx, v in enumerate(values):
        if random.random() < DEVICE_GLITCH_PROB:
            spike = random.uniform(0.15, 0.35) * clip_span * random.choice([-1, 1])
            values[idx] = v + spike
            quality.append("garbled")
        else:
            quality.append("good")
    return values, quality, (direction, behavior) if abnormal else (None, "stable")

# --- Point-scale scoring (0-3), NEWS2-inspired, adapted to the vitals we have ---
def score_temperature(v):
    if v <= 95.0: return 3
    if v <= 96.8: return 1
    if v <= 100.4: return 0
    if v <= 102.2: return 1
    if v <= 104.0: return 2
    return 3

def score_spo2(v):
    if v <= 91: return 3
    if v <= 93: return 2
    if v <= 95: return 1
    return 0

def score_systolic_bp(v):
    if v <= 90: return 3
    if v <= 100: return 2
    if v <= 110: return 1
    if v <= 219: return 0
    return 3

def score_glucose(v):
    if v < 54: return 3
    if v < 70: return 2
    if v <= 180: return 0
    if v <= 250: return 1
    if v <= 400: return 2
    return 3

def score_spirometer(v):
    if v < 250: return 3
    if v < 350: return 2
    if v < 380: return 1
    return 0

VITAL_SCORERS = {
    "temperature": score_temperature,
    "blood_oxygen": score_spo2,
    "blood_pressure_systolic": score_systolic_bp,
    "blood_glucose": score_glucose,
    "spirometer": score_spirometer,
}

def build_early_warning_score(scoreable_series, start_dt):
    """
    Merge all vitals' (timestamp, raw_value) events into one composite EWS
    trajectory, forward-filling each vital's last known score. Returns the
    trajectory plus the summary stats used to label the episode.
    """
    events = []
    for vital_key, series in scoreable_series.items():
        scorer = VITAL_SCORERS[vital_key]
        for ts, val in series:
            events.append((ts, vital_key, scorer(val)))
    events.sort(key=lambda e: e[0])

    last_scores = {k: 0 for k in scoreable_series}
    trajectory, max_score, red_flag = [], 0, False
    for ts, vital_key, score in events:
        last_scores[vital_key] = score
        red_flag = red_flag or score >= 3
        total = sum(last_scores.values())
        max_score = max(max_score, total)
        trajectory.append({"timestamp": ts.isoformat(), "score": total})

    final_score = trajectory[-1]["score"] if trajectory else 0
    slope = 0.0
    if len(trajectory) >= 2:
        xs = [(datetime.fromisoformat(p["timestamp"]) - start_dt).total_seconds() / 3600 for p in trajectory]
        ys = [p["score"] for p in trajectory]
        mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
        denom = sum((x - mean_x) ** 2 for x in xs)
        if denom > 0:
            slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom

    is_critical = red_flag or max_score >= 5 or (slope > 0.4 and final_score >= 3)
    risk_level = "high" if (red_flag or max_score >= 7) else ("medium" if is_critical else "low")

    return {
        "trajectory": trajectory,
        "max_score": max_score,
        "final_score": final_score,
        "single_param_red_flag": red_flag,
        "trend_slope_per_hour": round(slope, 3),
        "is_critical": is_critical,
        "risk_level": risk_level,
    }

DEVICE_PREFIXES = {
    "temperature": "TEMP", "blood_oxygen": "SPO2", "blood_glucose": "GLUC",
    "spirometer": "SPIR", "blood_pressure": "BP",
}

def make_patient_devices():
    """One simulated device id per vital channel, reused across a patient's episodes."""
    return {vital: f"DEV-{prefix}-{make_object_id()[:8]}" for vital, prefix in DEVICE_PREFIXES.items()}

def generate_vital_episode(visit_date_iso, is_abnormal_patient, devices):
    """
    Build one monitoring episode (a visit) as a multi-vital time series: each
    vital is sampled on its own interval by its assigned device, then scored
    into a composite early warning score trajectory that determines
    is_critical/risk_level. Garbled (sensor-glitch) readings are kept in the
    output but excluded from scoring, matching how a real pipeline would
    quality-filter device data before it reaches a model.
    """
    start_dt = datetime.fromisoformat(visit_date_iso)
    duration_hours = random.randint(EPISODE_DURATION_MIN_HOURS, EPISODE_DURATION_MAX_HOURS)
    end_dt = start_dt + timedelta(hours=duration_hours)

    abnormal_vitals = set()
    if is_abnormal_patient and random.random() < 0.7:
        pool = ["temperature", "blood_pressure", "blood_oxygen", "blood_glucose", "weight"]
        abnormal_vitals = set(random.sample(pool, k=random.randint(1, 3)))

    readings = {}
    scoreable_series = {}

    for vital, profile in VITAL_PROFILES.items():
        lo, hi = VITAL_SAMPLING_INTERVALS_MINUTES[vital]
        timestamps = make_episode_timestamps(start_dt, duration_hours * 60, random.randint(lo, hi))
        values, quality, _ = gen_trend_series(timestamps, profile, vital in abnormal_vitals)
        readings[vital] = {
            "device_id": devices[vital],
            "samples": [{"timestamp": ts.isoformat(), "value": profile["fmt"](v), "quality": q}
                        for ts, v, q in zip(timestamps, values, quality)],
        }
        scoreable_series[vital] = [(ts, v) for ts, v, q in zip(timestamps, values, quality) if q == "good"]

    # Blood pressure: systolic + diastolic share one direction/behavior and one cuff reading.
    bp_lo, bp_hi = VITAL_SAMPLING_INTERVALS_MINUTES["blood_pressure"]
    bp_timestamps = make_episode_timestamps(start_dt, duration_hours * 60, random.randint(bp_lo, bp_hi))
    bp_abnormal = "blood_pressure" in abnormal_vitals
    direction = random.choice(["high", "low"]) if bp_abnormal else None
    behavior = (random.choices(["worsening", "recovering", "fluctuating"], weights=[0.5, 0.3, 0.2])[0]
                if bp_abnormal else None)
    systolic_vals, systolic_q, _ = gen_trend_series(bp_timestamps, BP_PROFILES["systolic"], bp_abnormal, direction, behavior)
    diastolic_vals, diastolic_q, _ = gen_trend_series(bp_timestamps, BP_PROFILES["diastolic"], bp_abnormal, direction, behavior)
    bp_quality = ["garbled" if (sq == "garbled" or dq == "garbled") else "good"
                  for sq, dq in zip(systolic_q, diastolic_q)]
    readings["blood_pressure"] = {
        "device_id": devices["blood_pressure"],
        "samples": [{"timestamp": ts.isoformat(), "value": f"{round(s)}/{round(d)}", "quality": q}
                    for ts, s, d, q in zip(bp_timestamps, systolic_vals, diastolic_vals, bp_quality)],
    }
    scoreable_series["blood_pressure_systolic"] = [
        (ts, s) for ts, s, q in zip(bp_timestamps, systolic_vals, bp_quality) if q == "good"
    ]

    ews = build_early_warning_score(scoreable_series, start_dt)

    weight = (f"{random.choice([random.randint(35, 44), random.randint(110, 145)])} kg"
              if "weight" in abnormal_vitals else f"{random.randint(50, 85)} kg")

    return {
        "episode_start": start_dt.isoformat(),
        "episode_end": end_dt.isoformat(),
        "duration_hours": duration_hours,
        "weight": weight,
        "readings": readings,
        "early_warning_score": ews,
        "stethoscope": f"https://teleconsult-bucket.s3.amazonaws.com/vital/stethoscope/audio_{make_object_id()}.mp3",
        "screenshot": f"https://teleconsult-bucket.s3.amazonaws.com/vital/screenshot/img_{make_object_id()}.png",
        "createdAt": start_dt.isoformat(),
        "updatedAt": end_dt.isoformat(),
        "deletedAt": None,
    }

# =========================
# GENERATOR FUNCTIONS
# =========================
def gen_tenants():
    tenants = []
    for i in range(1, NUM_TENANTS + 1):
        org = fake.company()
        now = make_iso_date(30)
        tenants.append({
            "tenant_id": i,
            "hospital_name": f"{org} Hospital",
            "organization_name": org,
            "domain_name": f"{org.lower().replace(' ', '').replace(',', '')}.example.com",
            "fullname": "Admin",
            "username": f"admin_{i}",
            "email": f"admin{i}@example.com",
            "mobile": fake.msisdn()[:10],
            "password": "$2b$10$hashedpasswordplaceholder",
            "type": "admin",
            "status": "active",
            "createdAt": now,
            "updatedAt": now,
            "deletedAt": None,
        })
    return tenants

def gen_kiosks(tenants, users_admin_ids):
    kiosks = []
    for tenant in tenants:
        for k in range(NUM_KIOSKS_PER_TENANT):
            now = make_iso_date(60)
            kiosks.append({
                "_id": make_object_id(),
                "tenant_id": tenant["tenant_id"],
                "reg_id": f"KIO{tenant['tenant_id']:02d}{k+1:03d}",
                "name": f"{fake.city()} Mobile Unit",
                "code": f"K{tenant['tenant_id']}{k+1:03d}",
                "address": fake.address().replace("\n", ", "),
                "email": f"kiosk{tenant['tenant_id']}{k+1}@example.com",
                "mobile": fake.msisdn()[:10],
                "status": "active",
                "created_by": random.choice(users_admin_ids) if users_admin_ids else make_object_id(),
                "updated_by": None,
                "deleted_by": None,
                "createdAt": now,
                "updatedAt": now,
                "deletedAt": None,
            })
    return kiosks

def gen_places(kiosks, admin_id):
    places = []
    for kiosk in kiosks:
        # Each kiosk has 1-3 places
        for _ in range(random.randint(1, 3)):
            now = make_iso_date(60)
            places.append({
                "_id": make_object_id(),
                "kiosk_id": kiosk["_id"],
                "place_name": random.choice([f"Bed-{random.randint(1,20)}", f"Ambulance-{random.randint(1,5)}"]),
                "place_type": random.choice(["bed", "ambulance"]),
                "status": "active",
                "created_by": admin_id,
                "updated_by": None,
                "deleted_by": None,
                "createdAt": now,
                "updatedAt": now,
                "deletedAt": None,
            })
    return places

def gen_users(tenants):
    users = []
    user_index = {"doctors": [], "patients": [], "paramedics": [], "frontdesk": [], "admins": []}
    admin_id_per_tenant = {}

    for tenant in tenants:
        tid = tenant["tenant_id"]
        # Admin first
        admin_id = make_object_id()
        admin_id_per_tenant[tid] = admin_id

        def make_user(utype, reg_prefix, counter):
            gender = random.choice(["male", "female"])
            first = fake.first_name_male() if gender == "male" else fake.first_name_female()
            last = fake.last_name()
            title = "Dr" if utype == "doctor" else random.choice(["Mr", "Mrs", "Smt", "Sh"])
            uid = make_object_id()
            now = make_iso_date(180)
            user = {
                "_id": uid,
                "tenent_id": tid,  # Note: schema uses 'tenent_id' (typo preserved)
                "reg_id": f"{reg_prefix}{counter:03d}",
                "title": title,
                "firstname": first,
                "lastname": last,
                "fullname": f"{first} {last}",
                "username": f"{first.lower()}.{last.lower()}{counter}",
                "email": f"{first.lower()}.{last.lower()}{counter}@example.com",
                "password": "$2b$10$hashedpasswordplaceholder",
                "mobile": fake.msisdn()[:10],
                "aadhaar_no": fake.numerify("############"),
                "type": utype,
                "doctor_reg_no": f"MCI{random.randint(10000,99999)}" if utype == "doctor" else "",
                "professional_degree_id": make_object_id() if utype == "doctor" else None,
                "is_signature": utype == "doctor",
                "doctor_signature": f"https://example.com/signatures/{uid}.png" if utype == "doctor" else "",
                "dob": make_dob(25, 65) if utype != "patient" else make_dob(1, 85),
                "gender": gender,
                "maritalstatus": random.choice(["married", "single", "divorced", "widowed"]),
                "bloodgroup": random.choice(["A+", "A-", "AB-", "AB+", "B+", "B-", "O+", "O-", "Not aware"]),
                "generalmedicine": random.choice(["None", "Vitamin D", "Multivitamin", ""]),
                "allergies": random.choice(["None known", "Penicillin", "Dust", "Peanuts", ""]),
                "addressLane1": fake.street_address(),
                "addressLane2": "",
                "city": fake.city(),
                "state": fake.state(),
                "country": "India",
                "pincode": fake.postcode(),
                "status": "active",
                "availability_status": random.choice(["online", "offline", "busy"]),
                "profile_image": f"https://example.com/profile/{uid}.jpg",
                "device_type": random.choice(["ios", "android", "web"]),
                "device_token": fake.sha256(),
                "present_symptoms": {},  # CURRENT visit symptoms (paramedic-uploaded); patients populated below
                "createdAt": now,
                "updatedAt": now,
                "deletedAt": None,
            }
            return user

        # Doctors
        for i in range(1, NUM_DOCTORS_PER_TENANT + 1):
            u = make_user("doctor", "DT", i)
            users.append(u); user_index["doctors"].append(u["_id"])
        # Paramedics
        for i in range(1, NUM_PARAMEDICS_PER_TENANT + 1):
            u = make_user("paramedic", "PM", i)
            users.append(u); user_index["paramedics"].append(u["_id"])
        # Front-desk
        for i in range(1, NUM_FRONTDESK_PER_TENANT + 1):
            u = make_user("front-desk", "FD", i)
            users.append(u); user_index["frontdesk"].append(u["_id"])
        # Patients
        for i in range(1, NUM_PATIENTS_PER_TENANT + 1):
            u = make_user("patient", "PT", i)
            # Dedicated CURRENT-visit symptoms slot, uploaded by a paramedic.
            u["present_symptoms"] = make_present_symptoms(user_index["paramedics"])
            users.append(u); user_index["patients"].append(u["_id"])

        user_index["admins"].append(admin_id)

    return users, user_index, admin_id_per_tenant

def gen_doctor_slots(doctor_ids, admin_id):
    slots = []
    for did in doctor_ids:
        now = make_iso_date(30)
        slots.append({
            "_id": make_object_id(),
            "doctor_id": did,
            "Slot_start_date": "2026-01-01",
            "Slot_end_date": "2026-12-31",
            "start_date": "2026-01-01T00:00:00",
            "end_date": "2026-12-31T23:59:59",
            "days": {
                "mon": True, "tue": True, "wed": True,
                "thu": True, "fri": True,
                "sat": random.choice([True, False]),
                "sun": False,
            },
            # Critical: per schema, these are LOCAL time strings (no UTC conversion!)
            "begin_time": "09:00",
            "end_time": "17:00",
            "slot_duration_minutes": random.choice([15, 20, 30]),
            "status": "active",
            "created_by": admin_id,
            "updated_by": None,
            "deleted_by": None,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        })
    return slots

def gen_master_dict(name_list, admin_id):
    """Generate Symptoms or Diagnosis master records."""
    records = []
    for name in name_list:
        now = make_iso_date(200)
        records.append({
            "_id": make_object_id(),
            "name": name,
            "status": "active",
            "created_by": admin_id,
            "updated_by": admin_id,
            "deleted_by": None,
            "createdAt": now,
            "updatedAt": now,
            "deletedAt": None,
        })
    return records

def gen_clinical_data(user_index, symptoms_master, diagnosis_master):
    """Generate consultations, patient details, vitals, drugs, history for each patient."""
    consultations = []
    patient_details = []
    vital_details = []
    drugs = []
    past_med_history = []
    past_surgery = []
    family_history = []
    social_history = []

    abnormal_patient_count = int(len(user_index["patients"]) * ABNORMAL_PATIENT_RATIO)
    abnormal_patient_ids = set(random.sample(user_index["patients"], abnormal_patient_count))

    for pid in user_index["patients"]:
        is_abnormal_patient = pid in abnormal_patient_ids
        num_visits = random.randint(CONSULTATIONS_PER_PATIENT_MIN, CONSULTATIONS_PER_PATIENT_MAX)
        patient_devices = make_patient_devices()  # same simulated device per vital across this patient's visits

        # Generate visits in chronological order (oldest first)
        visit_dates = sorted([make_iso_date(365) for _ in range(num_visits)])
        vitals_array_for_patient = []

        for visit_idx, visit_date in enumerate(visit_dates):
            appointment_id = make_object_id()
            doctor_id = random.choice(user_index["doctors"])

            # Pick 1-4 symptoms
            chosen_symptoms = random.sample(symptoms_master, k=random.randint(1, 4))
            symptom_ids = [s["_id"] for s in chosen_symptoms]

            # Pick 1-2 diagnoses
            chosen_diagnoses = random.sample(diagnosis_master, k=random.randint(1, 2))
            diagnosis_ids = [d["_id"] for d in chosen_diagnoses]

            # Prescription gets its own ID
            prescription_id = make_object_id()

            # Consultation record
            consultations.append({
                "_id": make_object_id(),
                "appointment_id": appointment_id,
                "symptoms": symptom_ids,
                "diagnosis": diagnosis_ids,
                "prescription": prescription_id,
                "createdAt": visit_date,
                "updatedAt": visit_date,
                "deletedAt": None,
            })

            # PatientDetails record
            patient_details.append({
                "_id": make_object_id(),
                "patient_id": pid,
                "appointment_id": appointment_id,
                "symptoms": [{
                    "presenting_illness": random.choice(chosen_symptoms)["name"],
                    "duration_of_numbers": random.randint(1, 14),
                    "duration_type": random.choice(["day", "week", "month", "year"]),
                    "symptoms": [{"name": s["name"]} for s in chosen_symptoms],
                    "symptoms_add_note": fake.sentence(),
                    "createdAt": visit_date, "updatedAt": visit_date, "deletedAt": None,
                }],
                "tele_examination": [{
                    "description": fake.paragraph(nb_sentences=3),
                    "createdAt": visit_date, "updatedAt": visit_date, "deletedAt": None,
                }],
                "investigation": [{
                    "tests": [{"name": t} for t in random.sample(TEST_LIST, k=random.randint(1, 4))],
                    "investigation_add_note": fake.sentence(),
                    "createdAt": visit_date, "updatedAt": visit_date, "deletedAt": None,
                }],
                "diagnosis": [{
                    "differential_diagnosis": [{"name": d["name"]} for d in random.sample(diagnosis_master, k=2)],
                    "provisional_diagnosis": [{"name": d["name"]} for d in chosen_diagnoses],
                    "diagnosis": [{"name": d["name"]} for d in chosen_diagnoses],
                    "reports": "",
                    "differential_add_note": "",
                    "provisional_add_note": "",
                    "diagnosis_add_note": fake.sentence(),
                    "createdAt": visit_date, "updatedAt": visit_date, "deletedAt": None,
                }],
                "autoscope": [{
                    "autoscope_add_note": fake.sentence(),
                    "createdAt": visit_date, "updatedAt": visit_date, "deletedAt": None,
                }],
                "dermoscope": [{
                    "dermoscope_add_note": fake.sentence(),
                    "createdAt": visit_date, "updatedAt": visit_date, "deletedAt": None,
                }],
                "createdAt": visit_date,
                "updatedAt": visit_date,
                "deletedAt": None,
            })

            # Vitals: a full monitoring episode (multi-vital time series) for this visit,
            # labeled critical/normal from its early warning score trajectory.
            episode = generate_vital_episode(visit_date, is_abnormal_patient, patient_devices)
            episode["appointment_id"] = appointment_id
            vitals_array_for_patient.append(episode)

            # Drugs (prescription items)
            num_drugs = random.randint(1, 4)
            for _ in range(num_drugs):
                drug_name, dose = random.choice(DRUG_LIST)
                drugs.append({
                    "_id": make_object_id(),
                    "prescription_id": prescription_id,
                    "medicine_name": drug_name,
                    "medicine_dose": dose,
                    "medicine": make_object_id(),  # ref to Medicines master
                    "route": make_object_id(),     # ref to Routes master
                    "frequency": random.choice(["mon", "tue", "wed", "thu", "fri", "sat", "sun"]),
                    "duration": f"{random.randint(3, 14)} days",
                    "timings": random.choice(["morning", "afternoon", "evening", "night"]),
                    "instructions": random.choice(["morning", "afternoon", "evening", "night"]),
                    "createdAt": visit_date,
                    "updatedAt": visit_date,
                    "deletedAt": None,
                })

        # One VitalDetails document per patient, containing all visit vitals
        vital_details.append({
            "_id": make_object_id(),
            "patient_id": pid,
            "vitals": vitals_array_for_patient,
            "createdAt": visit_dates[0],
            "updatedAt": visit_dates[-1],
            "deletedAt": None,
        })

        # Past medical history (one per patient)
        past_med_history.append({
            "_id": make_object_id(),
            "patient_id": pid,
            "label": [{
                "pasthistory": [{
                    "name": random.choice(DIAGNOSIS_LIST),
                    "is_check": random.choice(["yes", "no"]),
                    "since": f"{random.randint(2010, 2024)}",
                    "frequency": random.randint(1, 12),
                    "per": random.choice(["month", "year", "week"]),
                } for _ in range(random.randint(0, 3))],
                "createdAt": visit_dates[0],
            }],
            "createdAt": visit_dates[0],
            "updatedAt": visit_dates[-1],
            "deletedAt": None,
        })

        # Past surgery (one per patient)
        had_surgery = random.random() < 0.25
        past_surgery.append({
            "_id": make_object_id(),
            "patient_id": pid,
            "label": [{
                "pastsurgeries": "yes" if had_surgery else "no",
                "typeofsurgery": random.choice(PAST_SURGERY_LIST) if had_surgery else "",
                "bloodtransfusion": random.choice(["yes", "no"]) if had_surgery else "no",
                "date": f"{random.randint(2010, 2024)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}" if had_surgery else "",
                "createdAt": visit_dates[0],
            }],
            "created_at": visit_dates[0],
            "updated_at": visit_dates[-1],
            "deleted_at": None,
        })

        # Family history (one per patient)
        family_history.append({
            "_id": make_object_id(),
            "patient_id": pid,
            "label": [{
                "familyhistoryofdisease": random.choice(["yes", "no"]),
                "parent": [{
                    "name": random.choice(["Father", "Mother", "Sibling"]),
                    "is_check": "yes",
                    "details": [{
                        "name": random.choice(FAMILY_DISEASE_LIST),
                        "is_check": "yes",
                        "since": f"{random.randint(1990, 2020)}",
                        "frequency": random.randint(1, 12),
                        "per": random.choice(["month", "year", "week"]),
                    }],
                } for _ in range(random.randint(1, 2))],
                "createdAt": visit_dates[0],
            }],
            "createdAt": visit_dates[0],
            "updatedAt": visit_dates[-1],
        })

        # Social history
        social_history.append({
            "_id": make_object_id(),
            "patient_id": pid,
            "label": [{
                "tobacco": random.choice(["occasional smoker", "mild smoker", "chain smoker", "no"]),
                "drinksAlcohol": random.choice(["drinks occasionally", "drinks mildly", "heavy drinker", "no"]),
                "exercise": random.choice(["no exercise", "mild exercise", "vigrous exercise"]),
                "exercise_description": fake.sentence(),
                "drugs": random.choice(["yes", "no"]),
                "drugs_description": "",
                "type": random.choice(["prescribed", "recreational"]),
                "sexualWellness": random.choice(["safe", "unsafe", "both", "none"]),
                "createdAt": visit_dates[0],
            }],
            "createdAt": visit_dates[0],
            "updatedAt": visit_dates[-1],
            "deletedAt": None,
        })

    return {
        "consultations": consultations,
        "patient_details": patient_details,
        "vital_details": vital_details,
        "drugs": drugs,
        "past_medical_history": past_med_history,
        "past_surgery": past_surgery,
        "family_history": family_history,
        "personal_social_history": social_history,
    }

# =========================
# OUTPUT / MAIN
# =========================
def write_json(filename, data):
    path = OUTPUT_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Wrote {len(data):>5} records -> {path}")

def main():
    print("=" * 60)
    print("Synthetic Tele-Consultation Data Generator")
    print("=" * 60)
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("\n[1/9] Generating tenants...")
    tenants = gen_tenants()

    print("[2/9] Generating users (doctors, patients, paramedics, front-desk)...")
    users, user_index, admin_id_per_tenant = gen_users(tenants)
    print(f"      Total users: {len(users)} "
          f"(doctors: {len(user_index['doctors'])}, "
          f"patients: {len(user_index['patients'])}, "
          f"paramedics: {len(user_index['paramedics'])}, "
          f"frontdesk: {len(user_index['frontdesk'])})")

    print("[3/9] Generating kiosks...")
    kiosks = gen_kiosks(tenants, user_index["admins"])

    print("[4/9] Generating places...")
    any_admin = user_index["admins"][0] if user_index["admins"] else make_object_id()
    places = gen_places(kiosks, any_admin)

    print("[5/9] Generating doctor slots...")
    doctor_slots = gen_doctor_slots(user_index["doctors"], any_admin)

    print("[6/9] Generating master dictionaries (symptoms, diagnoses)...")
    symptoms_master = gen_master_dict(SYMPTOM_LIST, any_admin)
    diagnosis_master = gen_master_dict(DIAGNOSIS_LIST, any_admin)

    print("[7/9] Generating clinical data (this is the big one)...")
    clinical = gen_clinical_data(user_index, symptoms_master, diagnosis_master)

    print("[8/9] Writing JSON files to ./output/ ...")
    write_json("tenants.json", tenants)
    write_json("users.json", users)
    write_json("kiosks.json", kiosks)
    write_json("places.json", places)
    write_json("doctor_slots.json", doctor_slots)
    write_json("symptoms_master.json", symptoms_master)
    write_json("diagnosis_master.json", diagnosis_master)
    write_json("consultations.json", clinical["consultations"])
    write_json("patient_details.json", clinical["patient_details"])
    write_json("vital_details.json", clinical["vital_details"])
    write_json("drugs.json", clinical["drugs"])
    write_json("past_medical_history.json", clinical["past_medical_history"])
    write_json("past_surgery.json", clinical["past_surgery"])
    write_json("family_history.json", clinical["family_history"])
    write_json("personal_social_history.json", clinical["personal_social_history"])

    print("\n[9/9] Done!")
    print(f"\nAll files are in: {OUTPUT_DIR.absolute()}")
    print("\nNext steps:")
    print("  1. Open any JSON file in a text editor to verify the data shape.")
    print("  2. (Optional) Set LOAD_TO_MONGO=True at the top of this script and re-run")
    print("     to load straight into MongoDB.")
    print("  3. Use vital_details.json's vitals[i].readings (time series) and")
    print("     vitals[i].early_warning_score.is_critical (label) to train a model.")

    # Optional: load to MongoDB
    if LOAD_TO_MONGO:
        print("\nLoading to MongoDB...")
        try:
            from pymongo import MongoClient
        except ImportError:
            print("  ERROR: pymongo not installed. Run: pip install pymongo")
            return
        client = MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        collection_map = {
            "tenants": tenants, "users": users, "kiosks": kiosks, "places": places,
            "doctor_slots": doctor_slots, "symptoms": symptoms_master,
            "diagnosis": diagnosis_master, **clinical,
        }
        for coll_name, docs in collection_map.items():
            db[coll_name].drop()
            if docs:
                db[coll_name].insert_many(docs)
                print(f"  Inserted {len(docs)} into {coll_name}")
        print(f"  All data loaded into MongoDB database: {MONGO_DB}")

if __name__ == "__main__":
    main()