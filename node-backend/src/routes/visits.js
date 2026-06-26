// GET /api/v1/patients/:id/visits — get all visits for a patient
import express from "express";
import { getDb } from "../db.js";
import { resolvePatientId } from "../friendlyIds.js";

const router = express.Router({ mergeParams: true });

router.get("/", async (req, res, next) => {
  try {

    console.log(`Fetching visits for patient ${req.params.id}`);
    const db = getDb();
    const realId = resolvePatientId(req.params.id) || req.params.id;

    const pd = await db.collection("patient_details")
      .find({ patient_id: realId })
      .toArray();

    const consultations = await db.collection("consultations").find({}).toArray();
    const drugs = await db.collection("drugs").find({}).toArray();
    const symptomsMaster = await db.collection("symptoms_master").find({}).toArray();
    const diagnosisMaster = await db.collection("diagnosis_master").find({}).toArray();

    const symptomById = Object.fromEntries(symptomsMaster.map(s => [s._id, s.name]));
    const diagById = Object.fromEntries(diagnosisMaster.map(d => [d._id, d.name]));

    const visits = pd.map((p) => {
      const consult = consultations.find(c => c.appointment_id === p.appointment_id);
      const prescribedDrugs = consult
        ? drugs.filter(d => d.prescription_id === consult.prescription).map(d => `${d.medicine_name} ${d.medicine_dose}`)
        : [];
      const symptoms = consult ? (consult.symptoms || []).map(s => symptomById[s] || s) : [];
      const diagnoses = consult ? (consult.diagnosis || []).map(d => diagById[d] || d) : [];
      const tests = (p.investigation || []).flatMap(i => (i.tests || []).map(t => t.name));

      return {
        date: p.createdAt || "",
        symptoms,
        diagnoses,
        medications: prescribedDrugs,
        tests,
      };
    });

    visits.sort((a, b) => new Date(b.date) - new Date(a.date));
    res.json({ visits });
  } catch (e) {
    next(e);
  }
});

export default router;
