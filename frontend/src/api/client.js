// Single axios instance for the whole app. No auth header (open demo).
// In dev, Vite proxies /api to :8000; in prod, Node serves this bundle so
// relative URLs just work. Override with VITE_API_BASE if needed.

import axios from "axios";

const baseURL = import.meta.env.VITE_API_BASE || "";

const client = axios.create({ baseURL, timeout: 300000 });

export const listPatients = (limit = 500) =>
  client.get(`/api/v1/patients?limit=${limit}`).then((r) => r.data.patients);

export const redflagCurrent = (patientId) =>
  client.post("/api/v1/redflag/current", { patient_id: patientId }).then((r) => r.data);

export const redflagDelta = (patientId) =>
  client.post("/api/v1/redflag/delta", { patient_id: patientId }).then((r) => r.data);

export const redflagMl = (patientId) =>
  client.post("/api/v1/redflag/ml", { patient_id: patientId }).then((r) => r.data);

export const summaryHistory = (patientId) =>
  client.post("/api/v1/summary/history", { patient_id: patientId }).then((r) => r.data);

export const chatAsk = (patientId, question, history) =>
  client
    .post("/api/v1/chat/ask", { patient_id: patientId, question, history })
    .then((r) => r.data);

export const getPatientVisits = (patientId) =>
  client.get(`/api/v1/patients/${patientId}/visits`).then((r) => r.data.visits);

export const latestVisit = (patientId) =>
  client.post("/api/v1/visit/latest", { patient_id: patientId }).then((r) => r.data);

export const getVitalsTimeseries = (patientId) =>
  client.get(`/api/v1/patients/${patientId}/vitals/timeseries`).then((r) => r.data);

// EventSource doesn't go through axios, so the live-stream URL is built directly.
export const vitalsLiveUrl = (patientId) =>
  `${baseURL}/api/v1/patients/${patientId}/vitals/live`;

export default client;
