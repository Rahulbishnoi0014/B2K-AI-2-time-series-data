// GET /api/v1/patients — list patients with friendly ids, sorted most-active first.
// Port of get_patient_list() from api_server.py.

import express from "express";
import { getDb } from "../db.js";
import { toFriendly } from "../friendlyIds.js";

const router = express.Router();

router.get("/", async (req, res, next) => {
  try {
    const limit = parseInt(req.query.limit, 10) || 500;
    const db = getDb();
    const users = await db.collection("users").find({ type: "patient" }).toArray();
    const pd = await db.collection("patient_details").find({}).toArray();

    const counts = {};
    for (const p of pd) counts[p.patient_id] = (counts[p.patient_id] || 0) + 1;

    const patients = users.map((u) => ({
      id: toFriendly(u._id), // friendly id the UI uses
      real_id: u._id,
      name: u.fullname || "Unknown",
      gender: u.gender || "",
      dob: u.dob || "",
      blood_group: u.bloodgroup || "",
      allergies: u.allergies || "",
      visit_count: counts[u._id] || 0,
    }));

    patients.sort((a, b) => {
      const na = a.id.startsWith("patient") ? parseInt(a.id.replace("patient", ""), 10) : 1e9;
      const nb = b.id.startsWith("patient") ? parseInt(b.id.replace("patient", ""), 10) : 1e9;
      return na - nb;
    });

    res.json({ patients: patients.slice(0, limit) });
  } catch (e) {
    next(e);
  }
});

export default router;
