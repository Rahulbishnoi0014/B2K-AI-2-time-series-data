import { useEffect, useState } from "react";
import { redflagDelta } from "../api/client.js";

export default function RedFlagDelta({ patientId }) {
  const [state, setState] = useState({ status: "idle" });

  useEffect(() => {
    if (!patientId) return;
    let active = true;
    setState({ status: "loading" });
    redflagDelta(patientId)
      .then((data) => active && setState({ status: "done", data }))
      .catch((e) => active && setState({ status: "error", message: e.message }));
    return () => {
      active = false;
    };
  }, [patientId]);

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Vitals Change Since Last Visit</h2>
        <span className="tag">Task 2 · deltas</span>
      </div>
      <div className="panel-body">
        {state.status === "idle" && <div className="empty-state">Select a patient.</div>}
        {state.status === "loading" && (
          <div className="loading">
            <div className="spinner" /> Comparing visits…
          </div>
        )}
        {state.status === "error" && <div className="error">Error: {state.message}</div>}
        {state.status === "done" && <Result data={state.data} />}
      </div>
    </div>
  );
}

function Result({ data }) {
  if (data.status === "single_visit_no_comparison")
    return <div className="empty-state">Only one visit on record. No comparison possible.</div>;
  if (data.status === "no_vitals")
    return <div className="empty-state">No vitals on record.</div>;

  const sev = data.overall_severity || "NORMAL";
  return (
    <>
      <div style={{ marginBottom: 12 }}>
        <span className={`sev-pill ${sev}`}>{sev}</span>
        <span style={{ fontSize: 12, color: "var(--ink-soft)", marginLeft: 8 }}>
          {data.days_between_visits} days between visits
        </span>
      </div>
      {data.flags && data.flags.length > 0 ? (
        data.flags.map((f, i) => (
          <div className={`flag-item sev-${f.severity}`} key={i}>
            <div className="flag-metric">
              {f.metric.replace("_delta", "").replace(/_/g, " ")} — {f.severity}
            </div>
            <div className="flag-reason">
              {f.previous} → {f.current}
              <div style={{ marginTop: 2, opacity: 0.85 }}>{f.reason}</div>
            </div>
          </div>
        ))
      ) : (
        <div className="ok-line">✓ Vitals stable compared to last visit.</div>
      )}
    </>
  );
}
