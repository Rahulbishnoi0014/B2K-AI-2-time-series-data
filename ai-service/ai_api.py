"""
Teleconsult AI Service (Python / FastAPI)
=========================================
Exposes ONLY the four AI tasks plus a reindex hook. This service is
internal — only the Node backend talks to it. It receives a real patient
ObjectId (Node has already resolved any friendly id) and returns task output.

Tasks:
  POST /ai/redflag/current  -> Task 1: absolute red-flag vitals
  POST /ai/redflag/delta    -> Task 2: cross-visit deltas
  POST /ai/summary          -> Task 3: LLM history summary
  POST /ai/chat             -> Task 4: patient-scoped RAG chat
  POST /ai/reindex          -> refresh one patient's vectors after a save

RUN:
  pip install -r requirements.txt
  uvicorn ai_api:app --host 0.0.0.0 --port 8001
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

from db import load_collection
from task1_redflag_vitals import analyze_latest_visit, analyze_vitals
from task2_redflag_deltas import analyze_patient_deltas
from task3_summarize_history import summarize_patient
from task4_rag_chatbot import ask as rag_ask
from task5_ml_risk_classifier import predict_episode
from visit_save import reindex_patient

app = FastAPI(title="Teleconsult AI Service", version="1.0.0")


# ---- helpers ----

def vital_record(real_id: str):
    """Find a patient's VitalDetails document. Same lookup api_server.py did."""
    for rec in load_collection("vital_details"):
        if rec["patient_id"] == real_id:
            return rec
    raise HTTPException(404, f"No vitals for patient {real_id}")


# ---- request models (patient_id is always a REAL ObjectId here) ----

class PatientReq(BaseModel):
    patient_id: str


class ChatReq(BaseModel):
    patient_id: str
    question: str
    history: Optional[list] = None


class ReindexReq(BaseModel):
    patient_id: str


# ---- routes ----

@app.get("/health")
def health():
    return {"status": "ok", "service": "teleconsult-ai"}


@app.post("/ai/redflag/current")
def redflag_current(req: PatientReq):
    return analyze_latest_visit(vital_record(req.patient_id))


@app.post("/ai/redflag/delta")
def redflag_delta(req: PatientReq):
    return analyze_patient_deltas(vital_record(req.patient_id))


@app.post("/ai/redflag/ml")
def redflag_ml(req: PatientReq):
    """Task 5: ML classifier's prediction on the latest episode, plus Task 1's
    NEWS2 call on that same episode so the UI can show both -- this is the
    rule the model was trained to approximate, so it's the right comparison."""
    doc = vital_record(req.patient_id)
    vitals = doc.get("vitals", [])
    if not vitals:
        return {"patient_id": req.patient_id, "status": "no_vitals"}

    episode = vitals[-1]
    news2 = analyze_vitals(episode)
    rule_is_critical = news2["risk_level"] in ("HIGH", "CRITICAL")
    try:
        prediction = predict_episode(episode)
    except FileNotFoundError:
        raise HTTPException(503, "ML model not found — run task5_ml_risk_classifier.py to train it first.")

    return {
        "patient_id": req.patient_id,
        "status": "ok",
        **prediction,
        "rule_is_critical": rule_is_critical,
        "rule_risk_level": news2["risk_level"],
        "agrees_with_rule": prediction["ml_is_critical"] == rule_is_critical,
    }


@app.post("/ai/summary")
def summary(req: PatientReq):
    result = summarize_patient(req.patient_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result

@app.post("/ai/visit/latest")
def present_symptoms(req: PatientReq):
    """Current present-visit symptoms from the patient's dedicated field."""
    users = load_collection("users")
    patient = next((u for u in users if u.get("_id") == req.patient_id), None)
    if not patient:
        return {"has_symptoms": False, "symptoms": [], "note": "", "updated_at": None}
    ps = patient.get("present_symptoms") or {}
    symptoms = ps.get("symptoms", [])
    return {
        "has_symptoms": bool(symptoms),
        "symptoms": symptoms,
        "note": ps.get("note", ""),
        "uploaded_by_role": ps.get("uploaded_by_role", ""),
        "updated_at": ps.get("updatedAt"),
    }


@app.post("/ai/chat")
def chat(req: ChatReq):
    try:
        answer, new_history, patient_name = rag_ask(
            req.patient_id, req.question, conversation_history=req.history
        )
    except Exception as e:
        raise HTTPException(500, f"Chat failed: {e}")
    return {
        "patient_name": patient_name,
        "question": req.question,
        "answer": answer,
        "conversation_history": new_history,
    }


@app.post("/ai/reindex")
def reindex(req: ReindexReq):
    ok = reindex_patient(req.patient_id)
    return {"reindexed": ok}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
