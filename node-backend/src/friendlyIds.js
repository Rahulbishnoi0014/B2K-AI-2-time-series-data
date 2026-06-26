// Friendly patient IDs — direct port of build_friendly_id_map / resolve_patient_id
// from the original api_server.py.
//
// Patients are exposed as patient001..patientNNN, sorted by visit count
// descending (patient001 = most visits). Node resolves friendly -> real
// before calling the Python AI service, and swaps real -> friendly on the
// way back so the browser only ever sees friendly ids.

import { getDb } from "./db.js";

let friendlyToReal = {};
let realToFriendly = {};

export async function buildFriendlyIdMap() {
  const db = getDb();
  const patients = await db.collection("users").find({ type: "patient" }).toArray();
  const pd = await db.collection("patient_details").find({}).toArray();

  const counts = {};
  for (const p of pd) counts[p.patient_id] = (counts[p.patient_id] || 0) + 1;

  patients.sort((a, b) => (counts[b._id] || 0) - (counts[a._id] || 0));

  friendlyToReal = {};
  realToFriendly = {};
  patients.forEach((u, i) => {
    const friendly = `patient${String(i + 1).padStart(3, "0")}`;
    friendlyToReal[friendly] = u._id;
    realToFriendly[u._id] = friendly;
  });

  console.log(`[friendlyIds] mapped ${patients.length} patients`);
  return patients.length;
}

export function resolvePatientId(maybeFriendly) {
  if (!maybeFriendly) {
    const e = new Error("patient_id required");
    e.status = 400;
    throw e;
  }
  const s = String(maybeFriendly).trim().toLowerCase();
  if (friendlyToReal[s]) return friendlyToReal[s];
  if (realToFriendly[maybeFriendly]) return maybeFriendly; // already a real id
  const e = new Error(`Unknown patient: ${maybeFriendly}`);
  e.status = 404;
  throw e;
}

export const toFriendly = (realId) => realToFriendly[realId] || realId;
export const visitCount = () => Object.keys(friendlyToReal).length;
