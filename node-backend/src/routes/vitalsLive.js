// GET /api/v1/patients/:id/vitals/live — Server-Sent Events stream that
// REPLAYS a patient's latest monitoring episode in chronological order, time-
// compressed into PLAYBACK_MS wall-clock seconds. Same recorded data as
// vitalsTimeseries.js, just delivered the way a live device would: one
// reading at a time, in the order it actually occurred.
import express from "express";
import { getDb } from "../db.js";
import { resolvePatientId } from "../friendlyIds.js";
import { parseNum, parseBp, findLatestEpisode } from "../lib/vitalsParse.js";

const router = express.Router({ mergeParams: true });

const PLAYBACK_MS = 25000; // full episode (6-24h) compressed into ~25s

function buildEvents(episode) {
  const readings = episode.readings || {};
  const events = [];

  for (const [vital, channel] of Object.entries(readings)) {
    for (const s of channel.samples || []) {
      if (vital === "blood_pressure") {
        const [systolic, diastolic] = parseBp(s.value);
        events.push({ vital, t: s.timestamp, systolic, diastolic, quality: s.quality });
      } else {
        events.push({ vital, t: s.timestamp, v: parseNum(s.value), quality: s.quality });
      }
    }
  }
  events.sort((a, b) => new Date(a.t) - new Date(b.t));

  const startMs = new Date(episode.episode_start).getTime();
  const endMs = new Date(episode.episode_end).getTime();
  const realDurationMs = Math.max(1, endMs - startMs);

  return events.map((ev) => ({
    ...ev,
    delayMs: Math.min(PLAYBACK_MS, Math.max(0, ((new Date(ev.t) - startMs) / realDurationMs) * PLAYBACK_MS)),
  }));
}

router.get("/", async (req, res, next) => {
  try {
    const db = getDb();
    const realId = resolvePatientId(req.params.id) || req.params.id;

    const episode = await findLatestEpisode(db, realId);
    if (!episode) {
      res.status(404).json({ detail: "No vitals for this patient" });
      return;
    }

    const events = buildEvents(episode);

    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    });

    const send = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);

    send("start", {
      episode_start: episode.episode_start,
      episode_end: episode.episode_end,
      duration_hours: episode.duration_hours,
      playback_ms: PLAYBACK_MS,
      ews: episode.early_warning_score || null,
    });

    const timers = events.map((ev) => setTimeout(() => send("reading", ev), ev.delayMs));
    timers.push(
      setTimeout(() => {
        send("done", {});
        res.end();
      }, PLAYBACK_MS + 200)
    );

    req.on("close", () => timers.forEach(clearTimeout));
  } catch (e) {
    next(e);
  }
});

export default router;
