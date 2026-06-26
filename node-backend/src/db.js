// Storage selector — flip the whole backend with one env var.
//
//   USE_MONGO=false  (default) → JSON files in DATA_DIR (../ai-service/output)
//   USE_MONGO=true            → local or remote MongoDB at MONGO_URI
//
// Both stores expose the SAME surface: getDb().collection(name) with
// find / findOne / insertOne / insertMany / updateOne. The route files never
// know which backend is active, so switching is purely an env-var change —
// and it matches the Python side's own USE_MONGO flag, keeping both backends
// on the same source of truth.
//
// NOTE: the generator stores _id as a 24-char hex STRING, not an ObjectId,
// so all queries use plain string _id values. Do NOT wrap ids in ObjectId().

import { makeJsonStore } from "./jsonStore.js";

const USE_MONGO = (process.env.USE_MONGO || "false").toLowerCase() === "true";
const MONGO_URI = process.env.MONGO_URI || "mongodb://localhost:27017";
const MONGO_DB = process.env.MONGO_DB || "teleconsult_dummy";

let store;
let mongoClient;

export async function connectDb() {
  if (store) return store;

  if (USE_MONGO) {
    const { MongoClient } = await import("mongodb");
    mongoClient = new MongoClient(MONGO_URI);
    await mongoClient.connect();
    const db = mongoClient.db(MONGO_DB);
    console.log(`[storage] MongoDB at ${MONGO_URI}/${MONGO_DB}`);
    store = db; // native driver already exposes .collection(name)
  } else {
    store = makeJsonStore();
  }
  return store;
}

export function getDb() {
  if (!store) throw new Error("Storage not initialized — call connectDb() first");
  return store;
}

export function isMongo() {
  return USE_MONGO;
}
