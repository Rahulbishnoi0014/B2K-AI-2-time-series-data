// JSON-file storage backend.
// Implements the small slice of the Mongo collection API that the routes use
// (find / findOne / insertOne / insertMany / updateOne with $push & $set),
// reading and writing the same output/*.json files the Python AI service reads
// when USE_MONGO=false. This keeps the two backends pointed at one source of
// truth in local mode.
//
// Writes are atomic (temp file + rename) and serialized per-file with an
// in-process lock, mirroring the original visit_save.py behaviour.

import fs from "fs";
import path from "path";

const DATA_DIR = path.resolve(process.env.DATA_DIR || "../ai-service/output");

// Per-file promise chain so concurrent writes to the same collection serialize.
const writeChains = {};

function filePath(name) {
  return path.join(DATA_DIR, `${name}.json`);
}

function readFileSync(name) {
  const p = filePath(name);
  if (!fs.existsSync(p)) return [];
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

function writeAtomic(name, data) {
  const p = filePath(name);
  const tmp = `${p}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2));
  fs.renameSync(tmp, p);
}

// Serialize a mutation against one collection file.
function withLock(name, fn) {
  const prev = writeChains[name] || Promise.resolve();
  const next = prev.then(fn, fn);
  // Keep the chain alive but swallow errors so one failure doesn't poison it.
  writeChains[name] = next.catch(() => {});
  return next;
}

// Minimal query matcher: supports plain equality and {$regex,$options:'i'}.
function matches(doc, query) {
  return Object.entries(query).every(([k, v]) => {
    if (v && typeof v === "object" && v.$regex !== undefined) {
      const flags = v.$options || "";
      return new RegExp(v.$regex, flags).test(doc[k] ?? "");
    }
    return doc[k] === v;
  });
}

class JsonCollection {
  constructor(name) {
    this.name = name;
  }

  find(query = {}) {
    const all = readFileSync(this.name);
    const filtered = Object.keys(query).length
      ? all.filter((d) => matches(d, query))
      : all;
    // Return an object with toArray() to match the Mongo driver surface.
    return { toArray: async () => filtered };
  }

  async findOne(query = {}) {
    const all = readFileSync(this.name);
    return all.find((d) => matches(d, query)) || null;
  }

  async insertOne(doc) {
    return withLock(this.name, () => {
      const all = readFileSync(this.name);
      all.push(doc);
      writeAtomic(this.name, all);
      return { insertedId: doc._id };
    });
  }

  async insertMany(docs) {
    return withLock(this.name, () => {
      const all = readFileSync(this.name);
      all.push(...docs);
      writeAtomic(this.name, all);
      return { insertedCount: docs.length };
    });
  }

  // Supports { $set: {...}, $push: { field: value } } on the first match.
  async updateOne(query, update) {
    return withLock(this.name, () => {
      const all = readFileSync(this.name);
      const doc = all.find((d) => matches(d, query));
      if (!doc) return { matchedCount: 0, modifiedCount: 0 };
      if (update.$set) Object.assign(doc, update.$set);
      if (update.$push) {
        for (const [field, value] of Object.entries(update.$push)) {
          if (!Array.isArray(doc[field])) doc[field] = [];
          doc[field].push(value);
        }
      }
      writeAtomic(this.name, all);
      return { matchedCount: 1, modifiedCount: 1 };
    });
  }
}

export function makeJsonStore() {
  if (!fs.existsSync(DATA_DIR)) {
    throw new Error(
      `JSON data dir not found: ${DATA_DIR}. Run the generator first, or set DATA_DIR.`
    );
  }
  console.log(`[storage] JSON files at ${DATA_DIR}`);
  return {
    collection: (name) => new JsonCollection(name),
  };
}
