import { useState } from "react";
export default function PatientBar({ patients, current, onSelect }) {
  const [manual, setManual] = useState("");
  const [error, setError] = useState("");

  function loadManual() {
    const raw = manual.trim();
    if (!raw) return;
    const found = patients.find((p) =>
      p.id === raw.toLowerCase() ||
      p.real_id === raw ||
      p.id === `patient${raw.padStart(3, "0")}` ||
      p.name?.toLowerCase().includes(raw.toLowerCase())
    );
    if (found) {
      onSelect(found);
      setManual("");
      setError("");
    } else {
      setError(`Patient "${raw}" not found.`);
    }
  }

  return (
    <div className="patient-bar">
      <select
        value={current?.id || ""}
        onChange={(e) => {
          const p = patients.find((x) => x.id === e.target.value);
          if (p) { onSelect(p); setError(""); }
        }}
      >
        <option value="" disabled>Select a patient…</option>
        {patients.map((p) => (
          <option key={p.id} value={p.id}>
            {p.id} — {p.name} ({p.visit_count} visits)
          </option>
        ))}
      </select>
      <input
        value={manual}
        placeholder="patient001"
        onChange={(e) => { setManual(e.target.value); setError(""); }}
        onKeyDown={(e) => e.key === "Enter" && loadManual()}
      />
      <button className="btn secondary" onClick={loadManual}>Load</button>
      {error && <span style={{ color: "var(--critical)", fontSize: "0.85rem" }}>{error}</span>}
      {current && !error && (
        <div className="patient-info">
          <span><strong>{current.name}</strong></span>
          <span><strong>DOB:</strong> {current.dob || "?"}</span>
          <span><strong>Gender:</strong> {current.gender || "?"}</span>
          <span><strong>Blood:</strong> {current.blood_group || "?"}</span>
          <span><strong>Allergies:</strong> {current.allergies || "none"}</span>
          <span><strong>Visits:</strong> {current.visit_count}</span>
        </div>
      )}
    </div>
  );
}