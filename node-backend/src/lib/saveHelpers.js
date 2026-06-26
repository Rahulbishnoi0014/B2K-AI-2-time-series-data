// Helpers ported from the original visit_save.py.
// makeObjectId(): 24-char hex string matching the generator's id format.
// ensureInMaster(): upsert a symptom/diagnosis name into its master collection
//                   (case-insensitive), returning the master record's _id.

import { getDb } from "../db.js";

export function makeObjectId() {
  const hex = "0123456789abcdef";
  let s = "";
  for (let i = 0; i < 24; i++) s += hex[Math.floor(Math.random() * 16)];
  return s;
}

export function nowIso() {
  return new Date().toISOString();
}

/**
 * Add `name` to a master collection if not already present (case-insensitive).
 * Returns the master record's _id, or null for empty input.
 */
export async function ensureInMaster(name, collectionName, adminId) {
  if (!name || !name.trim()) return null;
  const db = getDb();
  const clean = name.trim();
  const existing = await db
    .collection(collectionName)
    .findOne({ name: { $regex: `^${escapeRegex(clean)}$`, $options: "i" } });
  if (existing) return existing._id;

  const now = nowIso();
  const record = {
    _id: makeObjectId(),
    name: clean,
    status: "active",
    created_by: adminId,
    updated_by: adminId,
    deleted_by: null,
    createdAt: now,
    updatedAt: now,
    deletedAt: null,
  };
  await db.collection(collectionName).insertOne(record);
  return record._id;
}

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
