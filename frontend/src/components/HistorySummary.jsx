import { useEffect, useState } from "react";
import { summaryHistory } from "../api/client.js";

export default function HistorySummary({ patientId }) {
  const [state, setState] = useState({ status: "idle" });

  useEffect(() => {
    if (!patientId) return;
    let active = true;
    setState({ status: "loading" });
    summaryHistory(patientId)
      .then((data) => active && setState({ status: "done", data }))
      .catch((e) => active && setState({ status: "error", message: e.message }));
    return () => { active = false; };
  }, [patientId]);

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>AI History Summary</h2>
        <span className="tag">Task 3 · LLM</span>
      </div>
      <div className="panel-body">
        {state.status === "idle" && <div className="empty-state">Select a patient.</div>}
        {state.status === "loading" && (
          <div className="loading">
            <div className="spinner" /> AI generating summary… (30–90 seconds)
          </div>
        )}
        {state.status === "error" && (
          <div className="error">
            Error: {state.message}
            <br />
            <small>The LLM tunnel may be down. Restart the Kaggle notebook if needed.</small>
          </div>
        )}
        {state.status === "done" && <Result data={state.data} />}
      </div>
    </div>
  );
}

// Backend prompts for exactly 4 labeled lines now (CURRENT MEDS / CHANGES /
// TESTS / TREND) -- parse those directly instead of guessing at format.
const LABELS = ["CURRENT MEDS", "CHANGES", "TESTS", "TREND"];

function parseSummary(raw) {
  const found = {};
  for (const line of raw.split("\n").map((l) => l.trim()).filter(Boolean)) {
    for (const label of LABELS) {
      const m = line.match(new RegExp(`^${label}\\s*:\\s*(.*)$`, "i"));
      if (m) found[label] = m[1].trim();
    }
  }
  return found;
}

function chipsOrNone(value) {
  if (!value || /^none\.?$/i.test(value)) return null;
  return value.split(",").map((s) => s.trim().replace(/\.$/, "")).filter(Boolean);
}

function Result({ data }) {
  const raw = (data.summary || "").replace(/\*\*/g, "").trim();
  const parsed = parseSummary(raw);
  const meds = chipsOrNone(parsed["CURRENT MEDS"]);
  const tests = chipsOrNone(parsed["TESTS"]);
  const changes = parsed["CHANGES"] && !/^none\.?$/i.test(parsed["CHANGES"]) ? parsed["CHANGES"] : null;
  const trend = parsed["TREND"];
  const hasStructure = meds || tests || changes || trend;

  return (
    <>
      <div className="summary-meta">
        {data.visits_analyzed} visits · {data.elapsed_seconds}s
      </div>
      {hasStructure ? (
        <div className="summary-compact">
          {trend && <p className="summary-trend">{trend}</p>}
          {meds && (
            <div>
              <span className="summary-label">Current Meds</span>
              <div className="summary-tests">
                {meds.map((m, i) => (
                  <span key={i} className="test-chip">{m}</span>
                ))}
              </div>
            </div>
          )}
          {changes && (
            <p className="summary-line">
              <span className="summary-label">Changes</span>
              {changes}
            </p>
          )}
          {tests && (
            <div>
              <span className="summary-label">Recurring Tests</span>
              <div className="summary-tests">
                {tests.map((t, i) => (
                  <span key={i} className="test-chip">{t}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <p className="summary-line">{raw}</p>
      )}
      {data.needs_review && data.hallucination_warnings?.length > 0 && (
        <div className="hallucination-warning">
          ⚠ Hallucination guard — <strong>{data.hallucination_warnings.join(", ")}</strong>. Review carefully.
        </div>
      )}
    </>
  );
}