import { useEffect, useState } from "react";
import { redflagCurrent } from "../api/client.js";

const VITALS = [
  ["Weight", "weight"],
  ["Temp", "temperature"],
  ["BP", "blood_pressure"],
  ["SpO2", "blood_oxygen"],
  ["Glucose", "blood_glucose"],
];

function fmtDate(d) {
  if (!d) return "?";
  try {
    return new Date(d).toLocaleDateString();
  } catch {
    return d;
  }
}

export default function RedFlagCurrent({ patientId }) {
  const [state, setState] = useState({ status: "idle" });

  useEffect(() => {
    if (!patientId) return;
    let active = true;
    setState({ status: "loading" });
    redflagCurrent(patientId)
      .then((data) => active && setState({ status: "done", data }))
      .catch((e) => active && setState({ status: "error", message: e.message }));
    return () => {
      active = false;
    };
  }, [patientId]);

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Current Vitals Red Flags</h2>
        <span className="tag">Task 1 · NEWS2 rules</span>
      </div>
      <div className="panel-body">
        {state.status === "idle" && <div className="empty-state">Select a patient.</div>}
        {state.status === "loading" && (
          <div className="loading">
            <div className="spinner" /> Analyzing vitals…
          </div>
        )}
        {state.status === "error" && <div className="error">Error: {state.message}</div>}
        {state.status === "done" && <Result data={state.data} />}
      </div>
    </div>
  );
}

function Result({ data }) {
  const v = data.vitals || {};
  const sev = data.overall_severity || "NORMAL";
  return (
    <>
      <div style={{ marginBottom: 12 }}>
        <span className={`sev-pill ${sev}`}>{sev}</span>
        <span style={{ fontSize: 12, color: "var(--ink-soft)", marginLeft: 8 }}>
          Reading: {fmtDate(data.reading_date)}
        </span>
      </div>
      <div className="vitals-row">
        {VITALS.map(([label, key]) => (
          <div className="vital-box" key={key}>
            <div className="label">{label}</div>
            <div className="value">{v[key] || "—"}</div>
          </div>
        ))}
      </div>
      {data.flags && data.flags.length > 0 ? (
        <div style={{ marginTop: 12 }}>
          {data.flags.map((f, i) => (
            <div className={`flag-item sev-${f.severity}`} key={i}>
              <div className="flag-metric">
                {f.metric} — {f.severity}
              </div>
              <div className="flag-reason">{f.reason}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="ok-line">✓ All vitals within normal range.</div>
      )}
    </>
  );
}
