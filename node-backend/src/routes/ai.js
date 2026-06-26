// AI proxy — the four tasks live in the Python service. Node resolves the
// friendly id to a real ObjectId, forwards the request, and puts the friendly
// id back in the response so the browser never sees raw ids.
//
// Public paths kept identical to the original FastAPI server so the React
// frontend's calls are unchanged:
//   POST /api/v1/redflag/current
//   POST /api/v1/redflag/delta
//   POST /api/v1/summary/history
//   POST /api/v1/chat/ask

import express from "express";
import axios from "axios";
import { resolvePatientId } from "../friendlyIds.js";

const router = express.Router();
const AI = process.env.AI_SERVICE_URL || "http://localhost:8001";

// Generic proxy for endpoints that only need a patient_id.
function patientProxy(aiPath) {
  return async (req, res, next) => {
    try {
      const realId = resolvePatientId(req.body.patient_id);
      const { data } = await axios.post(
        `${AI}${aiPath}`,
        { patient_id: realId },
        { timeout: 300000 } // LLM tasks can take a while
      );
      res.json({ ...data, patient_id: req.body.patient_id });
    } catch (e) {
      next(normalizeAxiosError(e));
    }
  };
}

router.post("/redflag/current", patientProxy("/ai/redflag/current"));
router.post("/visit/latest", patientProxy("/ai/visit/latest"));
router.post("/redflag/delta", patientProxy("/ai/redflag/delta"));
router.post("/redflag/ml", patientProxy("/ai/redflag/ml"));
router.post("/summary/history", patientProxy("/ai/summary"));

// Chat needs question + history too.
router.post("/chat/ask", async (req, res, next) => {
  try {
    const realId = resolvePatientId(req.body.patient_id);
    const { data } = await axios.post(
      `${AI}/ai/chat`,
      {
        patient_id: realId,
        question: req.body.question,
        history: req.body.history || null,
      },
      { timeout: 300000 }
    );
    res.json({ ...data, patient_id: req.body.patient_id });
  } catch (e) {
    next(normalizeAxiosError(e));
  }
});

function normalizeAxiosError(e) {
  if (e.response) {
    const err = new Error(e.response.data?.detail || "AI service error");
    err.status = e.response.status;
    return err;
  }
  if (e.code === "ECONNREFUSED") {
    const err = new Error("AI service unreachable — is the Python service running?");
    err.status = 503;
    return err;
  }
  return e;
}

export default router;
