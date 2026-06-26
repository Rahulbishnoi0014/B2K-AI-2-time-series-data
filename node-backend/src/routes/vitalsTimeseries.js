// GET /api/v1/patients/:id/vitals/timeseries — the latest visit's full
// monitoring episode (every vital's sampled readings + the EWS trajectory),
// for the dashboard to render as a live-looking stream instead of one value.
import express from "express";
import { getDb } from "../db.js";
import { resolvePatientId } from "../friendlyIds.js";
import { parseNum, parseBp, findLatestEpisode } from "../lib/vitalsParse.js";

const router = express.Router({ mergeParams: true });

router.get("/", async (req, res, next) => {
  try {
    const db = getDb();
    const realId = resolvePatientId(req.params.id) || req.params.id;

    const episode = await findLatestEpisode(db, realId);
    if (!episode) {
      return res.json({ patient_id: req.params.id, status: "no_vitals" });
    }

    const readings = episode.readings || {};

    const channels = {};
    for (const [vital, channel] of Object.entries(readings)) {
      if (vital === "blood_pressure") {
        channels.blood_pressure = {
          device_id: channel.device_id,
          points: (channel.samples || []).map((s) => {
            const [systolic, diastolic] = parseBp(s.value);
            return { t: s.timestamp, systolic, diastolic, quality: s.quality };
          }),
        };
      } else {
        channels[vital] = {
          device_id: channel.device_id,
          points: (channel.samples || []).map((s) => ({
            t: s.timestamp,
            v: parseNum(s.value),
            quality: s.quality,
          })),
        };
      }
    }

    res.json({
      patient_id: req.params.id,
      status: "ok",
      episode_start: episode.episode_start,
      episode_end: episode.episode_end,
      duration_hours: episode.duration_hours,
      weight: episode.weight,
      vitals: channels,
      ews: episode.early_warning_score || null,
    });
  } catch (e) {
    next(e);
  }
});

export default router;
