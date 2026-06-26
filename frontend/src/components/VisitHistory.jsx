import { useEffect, useState } from "react";
import { getPatientVisits } from "../api/client.js";

export default function VisitHistory({ patientId }) {
  const [state, setState] = useState({ status: "idle" });

  useEffect(() => {
    if (!patientId) return;
    let active = true;
    setState({ status: "loading" });
    getPatientVisits(patientId)
      .then((visits) => active && setState({ status: "done", visits }))
      .catch((e) => active && setState({ status: "error", message: e.message }));
    return () => { active = false; };
  }, [patientId]);

  return (
    <div className="panel" style={{ gridColumn: "1 / -1" }}>
      <div className="panel-head">
        <h2>Visit History</h2>
        <span className="tag">{state.visits?.length || 0} visits</span>
      </div>
      <div className="panel-body">
        {state.status === "loading" && <div className="loading"><div className="spinner" /> Loading visits…</div>}
        {state.status === "error" && <div className="error">Error: {state.message}</div>}
        {state.status === "done" && state.visits.length === 0 && <div className="empty-state">No visits on record.</div>}
        {state.status === "done" && state.visits.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table className="visit-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Symptoms</th>
                  <th>Diagnoses</th>
                  <th>Medications</th>
                  <th>Tests</th>
                </tr>
              </thead>
              <tbody>
                {state.visits.map((v, i) => (
                  <tr key={i}>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {v.date ? new Date(v.date).toLocaleDateString("en-IN") : "—"}
                    </td>
                    <td>{v.symptoms?.join(", ") || "—"}</td>
                    <td>{v.diagnoses?.join(", ") || "—"}</td>
                    <td>{v.medications?.join(", ") || "—"}</td>
                    <td>{v.tests?.join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}