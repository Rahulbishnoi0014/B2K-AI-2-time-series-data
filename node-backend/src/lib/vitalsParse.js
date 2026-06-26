// Shared helpers for reading a patient's latest monitoring episode out of
// vital_details, used by both the snapshot endpoint (vitalsTimeseries.js)
// and the live-replay endpoint (vitalsLive.js).

export function parseNum(s) {
  if (s == null) return null;
  const m = String(s).match(/-?\d+\.?\d*/);
  return m ? parseFloat(m[0]) : null;
}

export function parseBp(s) {
  const m = String(s || "").match(/(\d+)\s*\/\s*(\d+)/);
  return m ? [parseInt(m[1], 10), parseInt(m[2], 10)] : [null, null];
}

export async function findLatestEpisode(db, patientId) {
  const doc = await db.collection("vital_details").findOne({ patient_id: patientId });
  const vitals = doc?.vitals || [];
  if (!vitals.length) return null;
  return vitals[vitals.length - 1];
}
