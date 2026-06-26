import { useEffect, useState } from "react";
import { redflagMl } from "../api/client.js";

export default function RedFlagML({ patientId }) {
  const [state, setState] = useState({ status: "idle" });

  useEffect(() => {
    if (!patientId) return;
    let active = true;
    setState({ status: "loading" });
    redflagMl(patientId)
      .then((data) => active && setState({ status: "done", data }))
      .catch((e) => active && setState({ status: "error", message: e.message }));
    return () => {
      active = false;
    };
  }, [patientId]);

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>ML Predicted Risk</h2>
        <span className="tag">Task 5 · trained classifier</span>
      </div>
      <div className="panel-body">
        {state.status === "idle" && <div className="empty-state">Select a patient.</div>}
        {state.status === "loading" && (
          <div className="loading">
            <div className="spinner" /> Scoring vitals trend…
          </div>
        )}
        {state.status === "error" && <div className="error">Error: {state.message}</div>}
        {state.status === "done" && <Result data={state.data} />}
      </div>
    </div>
  );
}

function Result({ data }) {
  if (data.status === "no_vitals") {
    return <div className="empty-state">No vitals on record for this patient.</div>;
  }
  if (data.status !== "ok") {
    return <div className="empty-state">Model unavailable.</div>;
  }

  const mlSev = data.ml_is_critical ? "CRITICAL" : "NORMAL";
  const ruleSev = data.rule_is_critical ? "CRITICAL" : "NORMAL";
  const pct = Math.round(data.ml_risk_probability * 100);

  return (
    <>
      <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
        <span className={`sev-pill ${mlSev}`}>{mlSev}</span>
        <span style={{ fontSize: 12, color: "var(--ink-soft)" }}>
          ML risk probability: {pct}%
        </span>
      </div>

      <div
        style={{
          height: 8,
          borderRadius: 4,
          background: "var(--accent-soft)",
          overflow: "hidden",
          marginBottom: 12,
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${pct}%`,
            background: pct >= 50 ? "#c0392b" : "var(--accent)",
            transition: "width 0.3s ease",
          }}
        />
      </div>

      <div className="vital-stream-meta" style={{ marginBottom: 4 }}>
        NEWS2 rule says: <strong>{ruleSev}</strong> ({data.rule_risk_level})
      </div>
      <div className={`ok-line`} style={!data.agrees_with_rule ? { color: "#c0392b" } : undefined}>
        {data.agrees_with_rule ? "✓ ML agrees with the NEWS2 rule" : "⚠ ML disagrees with the NEWS2 rule"}
      </div>
      <div className="vital-stream-meta" style={{ marginTop: 8 }}>
        {data.model}
      </div>
    </>
  );
}
