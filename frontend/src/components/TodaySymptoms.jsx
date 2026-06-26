import { useEffect, useState } from "react";
import { latestVisit } from "../api/client.js";

function fmtDate(d) {
  if (!d) return "";
  try {
    return new Date(d).toLocaleString();
  } catch {
    return d;
  }
}

export default function TodaySymptoms({ patientId, refreshKey }) {
  const [state, setState] = useState({ status: "idle" });

  useEffect(() => {
    if (!patientId) return;
    let active = true;
    setState({ status: "loading" });
    latestVisit(patientId)
      .then((data) => active && setState({ status: "done", data }))
      .catch((e) => active && setState({ status: "error", message: e.message }));
    return () => {
      active = false;
    };
  }, [patientId, refreshKey]);

  return (
    <div className="panel today-panel">
      <div className="panel-head">
        <h2>Present Symptoms</h2>
        <span className="tag">Current visit · paramedic-uploaded</span>
      </div>
      <div className="panel-body">
        {state.status === "idle" && <div className="empty-state">Select a patient.</div>}
        {state.status === "loading" && (
          <div className="loading">
            <div className="spinner" /> Loading current symptoms…
          </div>
        )}
        {state.status === "error" && <div className="error">Error: {state.message}</div>}
        {state.status === "done" && <Content data={state.data} />}
      </div>
    </div>
  );
}

function Content({ data }) {
  if (!data.has_symptoms) {
    return (
      <div className="today-empty">
        No symptoms added for the current visit.
        <div className="today-empty-sub">
          Waiting for a paramedic to upload the patient&apos;s present symptoms.
        </div>
      </div>
    );
  }
  return (
    <>
      <div className="symptom-chips">
        {data.symptoms.map((s, i) => (
          <span className="symptom-chip" key={i}>
            {s}
          </span>
        ))}
      </div>
      {data.note && <div className="today-note">&ldquo;{data.note}&rdquo;</div>}
      <div className="today-meta">
        Uploaded {fmtDate(data.updated_at)}
        {data.uploaded_by_role ? ` · by ${data.uploaded_by_role}` : ""}
      </div>
    </>
  );
}