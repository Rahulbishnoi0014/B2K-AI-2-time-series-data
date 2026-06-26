// Teleconsult AI — Node/Express gateway.
// The only server the browser talks to. Handles patient/master/visit data
// against Mongo and proxies the four AI tasks to the Python service.
// No auth: open demo as requested.

import "./loadEnv.js";

import express from "express";
import cors from "cors";
import path from "path";
import { fileURLToPath } from "url";

import { connectDb } from "./db.js";
import { buildFriendlyIdMap, visitCount } from "./friendlyIds.js";
import patientsRouter from "./routes/patients.js";
import aiRouter from "./routes/ai.js";
import visitsRouter from "./routes/visits.js";
import vitalsTimeseriesRouter from "./routes/vitalsTimeseries.js";
import vitalsLiveRouter from "./routes/vitalsLive.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 8000;

const app = express();
app.use(cors());
app.use(express.json({ limit: "2mb" }));

// ---- API routes (paths identical to the original FastAPI server) ----
app.get("/health", (req, res) => res.json({ status: "ok", service: "teleconsult-node" }));
app.use("/api/v1/patients", patientsRouter);
app.use("/api/v1", aiRouter); // /api/v1/redflag/*, /summary/history, /chat/ask
app.use("/api/v1/patients/:id/visits", visitsRouter);
app.use("/api/v1/patients/:id/vitals/timeseries", vitalsTimeseriesRouter);
app.use("/api/v1/patients/:id/vitals/live", vitalsLiveRouter);

// ---- Serve the built React frontend (single shareable URL) ----
const FRONTEND_DIST =
  process.env.FRONTEND_DIST || path.resolve(__dirname, "../../frontend/dist");
app.use(express.static(FRONTEND_DIST));
app.get(/^(?!\/api).*/, (req, res) => {
  res.sendFile(path.join(FRONTEND_DIST, "index.html"), (err) => {
    if (err) res.status(404).send("Frontend not built yet. Run `npm run build` in frontend/.");
  });
});

// ---- Central error handler ----
app.use((err, req, res, next) => {
  const status = err.status || 500;
  if (status >= 500) console.error(err);
  res.status(status).json({ detail: err.message || "Internal error" });
});

async function start() {
  await connectDb();
  const n = await buildFriendlyIdMap();
  app.listen(PORT, () => {
    console.log("=".repeat(60));
    console.log("Tele-Consultation AI — Node gateway");
    console.log("=".repeat(60));
    console.log(`  URL:             http://localhost:${PORT}`);
    console.log(`  AI service:      ${process.env.AI_SERVICE_URL || "http://localhost:8001"}`);
    console.log(`  Patients loaded: ${n} (patient001 to patient${String(n).padStart(3, "0")})`);
    console.log("=".repeat(60));
  });
}

start().catch((e) => {
  console.error("Failed to start:", e);
  process.exit(1);
});
