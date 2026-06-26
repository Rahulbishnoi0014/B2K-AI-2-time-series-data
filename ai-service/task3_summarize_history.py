"""
Task 3: Patient History Summary (LLM-Powered)
==============================================
Generates a clinical summary of a patient's prescription and test history.
Uses the Kaggle-hosted Llama 3.1 8B model via the tunnel.

WHAT IT DOES:
1. Loads a patient's consultations, prescriptions, and test orders
2. Formats them into a structured prompt (chronological, oldest first)
3. Sends to the LLM with strict instructions to not invent anything
4. Validates the output by checking that every drug name mentioned
   actually appears in the source data (hallucination guard)

HALLUCINATION GUARD:
LLMs sometimes invent drug names. The post_validate() function extracts
every capitalized word from the summary and warns if any aren't in the
input. This is your safety net â€” never deploy LLM medical summaries
without one.

HOW TO RUN:
  1. Make sure your Kaggle Ollama tunnel is running (from kaggle_ollama_client.py)
  2. Update OLLAMA_URL in kaggle_ollama_client.py
  3. Run: python task3_summarize_history.py
  4. To summarize a specific patient: python task3_summarize_history.py <patient_id>
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Import the LLM client we already built
from kaggle_ollama_client import generate, check_connection


# =========================
# DATA LOADING
# =========================

def load_patient_history(patient_id, data_dir="output"):
    """
    Build a structured view of one patient's history from the JSON files.
    Returns a dict with consultations, drugs, tests, and metadata, sorted chronologically.
    """
    data_dir = Path(data_dir)

    # Load all related data
    with open(data_dir / "users.json") as f:
        users = json.load(f)
    with open(data_dir / "consultations.json") as f:
        consultations = json.load(f)
    with open(data_dir / "patient_details.json") as f:
        patient_details = json.load(f)
    with open(data_dir / "drugs.json") as f:
        drugs = json.load(f)
    with open(data_dir / "symptoms_master.json") as f:
        symptoms_master = json.load(f)
    with open(data_dir / "diagnosis_master.json") as f:
        diagnosis_master = json.load(f)

    # Find the patient
    patient = next((u for u in users if u["_id"] == patient_id), None)
    if not patient:
        return None

    # Index masters for fast lookup
    symptom_by_id = {s["_id"]: s["name"] for s in symptoms_master}
    diagnosis_by_id = {d["_id"]: d["name"] for d in diagnosis_master}

    # Filter patient_details for this patient
    pd_for_patient = [pd for pd in patient_details if pd["patient_id"] == patient_id]

    # For each PatientDetails, find the matching Consultation via appointment_id,
    # then attach the drugs from that prescription.
    visits = []
    for pd in pd_for_patient:
        appt_id = pd["appointment_id"]
        consult = next((c for c in consultations if c["appointment_id"] == appt_id), None)

        # Diagnosis names from the master IDs in the consultation
        diag_names = []
        if consult:
            diag_names = [diagnosis_by_id.get(did, "Unknown") for did in consult.get("diagnosis", [])]

        # Symptom names
        symptom_names = []
        if consult:
            symptom_names = [symptom_by_id.get(sid, "Unknown") for sid in consult.get("symptoms", [])]

        # Drugs in this prescription
        prescribed_drugs = []
        if consult:
            prescription_id = consult.get("prescription")
            for d in drugs:
                if d.get("prescription_id") == prescription_id:
                    prescribed_drugs.append({
                        "name": d.get("medicine_name", "Unknown"),
                        "dose": d.get("medicine_dose", ""),
                        "frequency": d.get("frequency", ""),
                        "duration": d.get("duration", ""),
                        "timings": d.get("timings", ""),
                    })

        # Tests ordered (from patient_details.investigation)
        tests_ordered = []
        for inv in pd.get("investigation", []):
            for t in inv.get("tests", []):
                tests_ordered.append(t.get("name", "Unknown"))

        visits.append({
            "date": pd.get("createdAt", ""),
            "symptoms": symptom_names,
            "diagnoses": diag_names,
            "tests_ordered": tests_ordered,
            "prescribed_drugs": prescribed_drugs,
        })

    # Sort chronologically (oldest first â€” LLM does better with that order)
    visits.sort(key=lambda v: v["date"])

    return {
        "patient_id": patient_id,
        "name": patient.get("fullname", "Unknown"),
        "age_dob": patient.get("dob", ""),
        "gender": patient.get("gender", ""),
        "allergies": patient.get("allergies", ""),
        "bloodgroup": patient.get("bloodgroup", ""),
        "visits": visits,
        "total_visits": len(visits),
    }


# =========================
# PROMPT FORMATTING
# =========================

def format_history_for_llm(patient_history):
    """Convert the patient_history dict into a clean text block for the LLM."""
    lines = [
        f"PATIENT: {patient_history['name']} (DOB: {patient_history['age_dob']}, "
        f"{patient_history['gender']}, Blood: {patient_history['bloodgroup']})",
        f"Allergies: {patient_history['allergies'] or 'None recorded'}",
        f"Total visits on record: {patient_history['total_visits']}",
        "",
        "VISIT HISTORY (oldest first):",
    ]

    for i, visit in enumerate(patient_history["visits"], 1):
        # Parse the date for cleaner display
        try:
            visit_date = datetime.fromisoformat(visit["date"]).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            visit_date = visit["date"]

        lines.append(f"\n[Visit {i} â€” {visit_date}]")
        if visit["symptoms"]:
            lines.append(f"  Symptoms: {', '.join(visit['symptoms'])}")
        if visit["diagnoses"]:
            lines.append(f"  Diagnoses: {', '.join(visit['diagnoses'])}")
        if visit["tests_ordered"]:
            lines.append(f"  Tests ordered: {', '.join(visit['tests_ordered'])}")
        if visit["prescribed_drugs"]:
            lines.append(f"  Prescribed:")
            for d in visit["prescribed_drugs"]:
                lines.append(f"    - {d['name']} {d['dose']}, {d['timings']}, for {d['duration']}")

    return "\n".join(lines)


# =========================
# HALLUCINATION GUARD
# =========================

def extract_drug_mentions(text):
    """
    Extract probable drug names from LLM output.
    Heuristic: any standalone capitalized word > 4 characters.
    Imperfect but catches obvious hallucinations.
    """
    import re
    # Find capitalized words (excluding common sentence-starters)
    candidates = re.findall(r"\b[A-Z][a-z]{4,}\b", text)
    # Filter out very common non-drug words
    stopwords = {
        "Patient", "Visit", "Test", "Tests", "Diagnosis", "Diagnoses",
        "Treatment", "History", "Summary", "Recently", "Currently",
        "Symptoms", "Allergies", "Medical", "Clinical", "Doctor",
        "Female", "Male", "Year", "Years", "Month", "Months", "Daily",
        "Twice", "Morning", "Evening", "Night", "Afternoon", "During",
        "Notable", "Significant", "Started", "Prescribed", "Ordered",
        "Continued", "Discontinued", "However", "Therefore", "Mellitus",
        "Disease", "Disorder", "Acute", "Chronic", "Possible", "Likely",
        "Stable", "Stopped", "Improving", "Worsening", "Insufficient",
        "Unclear", "Unknown", "Overall", "Across", "Visits",
    }
    return set(c for c in candidates if c not in stopwords)


def validate_summary(summary_text, source_text):
    """
    Check if every drug-like word in the summary appears in the source.
    Returns a list of suspicious mentions (likely hallucinations).
    """
    summary_drugs = extract_drug_mentions(summary_text)
    source_drugs = extract_drug_mentions(source_text)

    suspicious = []
    for drug in summary_drugs:
        if drug not in source_drugs:
            # Also check lowercase substring match in source
            if drug.lower() not in source_text.lower():
                suspicious.append(drug)

    return suspicious


# =========================
# MAIN SUMMARIZATION
# =========================

SYSTEM_PROMPT = """You are a clinical assistant producing an ULTRA-COMPACT summary for a doctor
who has seconds to scan it, not minutes to read it.

Strict rules:
- Do not invent any medications, tests, diagnoses, or events not in the records.
- Use only the drug names, test names, and diagnoses exactly as they appear.
- Output EXACTLY four lines, each starting with the label shown, nothing else
  before, after, or between them (no headers, no extra commentary).
- Each list is comma-separated short items only -- no full sentences inside lists.
- If a section has nothing to report, write "None" after its label."""


USER_PROMPT_TEMPLATE = """Below is a patient's complete history. Produce EXACTLY this four-line format,
keeping every line as short as possible while keeping every fact (drug names with
dose, test names):

CURRENT MEDS: <comma-separated "Name dose" list the patient is on right now, or None>
CHANGES: <comma-separated short items, e.g. "Started X", "Stopped Y", or None>
TESTS: <comma-separated names of tests ordered more than once, or None>
TREND: <max 1 short sentence: improving / stable / worsening / insufficient data, plus why>

PATIENT HISTORY:
{history}

Output only the four labeled lines. Nothing else."""


def summarize_patient(patient_id, data_dir="output"):
    """End-to-end: load patient, format prompt, call LLM, validate, return result."""
    history = load_patient_history(patient_id, data_dir)
    if not history:
        return {"error": f"Patient {patient_id} not found"}

    if not history["visits"]:
        return {
            "patient_id": patient_id,
            "name": history["name"],
            "summary": "No visit history on record.",
            "warnings": [],
        }

    history_text = format_history_for_llm(history)
    user_prompt = USER_PROMPT_TEMPLATE.format(history=history_text)

    print(f"Summarizing {history['name']} (id: {patient_id})...")
    print(f"  Visits: {history['total_visits']}")

    result = generate(user_prompt, system=SYSTEM_PROMPT, max_tokens=220, temperature=0.2)

    # Hallucination check
    suspicious = validate_summary(result["text"], history_text)

    return {
        "patient_id": patient_id,
        "name": history["name"],
        "visits_analyzed": history["total_visits"],
        "summary": result["text"],
        "elapsed_seconds": result["elapsed_seconds"],
        "hallucination_warnings": suspicious,
        "needs_review": len(suspicious) > 0,
    }


def find_interesting_patient(data_dir="output", min_visits=3):
    """Pick a patient with many visits â€” better demo material."""
    with open(Path(data_dir) / "patient_details.json") as f:
        patient_details = json.load(f)

    visit_counts = defaultdict(int)
    for pd in patient_details:
        visit_counts[pd["patient_id"]] += 1

    eligible = [(pid, count) for pid, count in visit_counts.items() if count >= min_visits]
    if not eligible:
        # Fall back to whoever has the most
        eligible = sorted(visit_counts.items(), key=lambda x: -x[1])
    eligible.sort(key=lambda x: -x[1])
    return eligible[0][0] if eligible else None


# =========================
# CLI
# =========================

if __name__ == "__main__":
    print("=" * 60)
    print("Task 3: Patient History Summarization")
    print("=" * 60)

    if not check_connection():
        print("\nFix the Kaggle tunnel before continuing.")
        raise SystemExit(1)

    # Use specific patient if provided, else pick an interesting one
    if len(sys.argv) > 1:
        patient_id = sys.argv[1]
    else:
        patient_id = find_interesting_patient()
        print(f"No patient ID specified. Using interesting one: {patient_id}")

    if not patient_id:
        print("ERROR: No patients found in the data. Run generate_synthetic_data.py first.")
        raise SystemExit(1)

    result = summarize_patient(patient_id)

    print("\n" + "=" * 60)
    print(f"SUMMARY for {result['name']}")
    print(f"({result['visits_analyzed']} visits, generated in {result.get('elapsed_seconds', '?')}s)")
    print("=" * 60)
    print(result["summary"])
    print("=" * 60)

    if result.get("needs_review"):
        print("\nâš ï¸  HALLUCINATION GUARD WARNING:")
        print(f"   The following terms appear in the summary but NOT in the source data:")
        for term in result["hallucination_warnings"]:
            print(f"   - {term}")
        print("   Review the summary carefully before showing to a clinician.")
    else:
        print("\nâœ“ Hallucination guard: all major terms in summary verified against source.")

    # Save to a file for inspection
    out_path = Path("output") / f"summary_{patient_id[:8]}.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nFull result saved to: {out_path}")