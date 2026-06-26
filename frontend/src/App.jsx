import { useEffect, useState } from "react";
import { listPatients } from "./api/client.js";
import PatientBar from "./components/PatientBar.jsx";
import RedFlagCurrent from "./components/RedFlagCurrent.jsx";
import RedFlagDelta from "./components/RedFlagDelta.jsx";
import HistorySummary from "./components/HistorySummary.jsx";
import ChatPanel from "./components/ChatPanel.jsx";
import VisitHistory from "./components/VisitHistory.jsx";
import TodaySymptoms from "./components/TodaySymptoms.jsx";
import VitalsTimeline from "./components/VitalsTimeline.jsx";
import RedFlagML from "./components/RedFlagML.jsx";

export default function App() {
  const [patients, setPatients] = useState([]);
  const [current, setCurrent] = useState(null);
  const [online, setOnline] = useState(null);

  async function loadPatients() {
    const list = await listPatients(500);
    setPatients(list);
  }

  useEffect(() => {
    loadPatients()
      .then(() => setOnline(true))
      .catch(() => setOnline(false));
  }, []);

  const panelKey = current && !current.notInList ? current.id : null;

  return (
    <>
      <header>
        <h1>B2K AI</h1>
        <span className="subtitle">Doctor Console · Synthetic Data Demo</span>
        <span className="spacer" />
        <span className="status">
          {online === null ? "connecting…" : online ? "● server online" : "● server offline"}
        </span>
      </header>

      <PatientBar patients={patients} current={current} onSelect={setCurrent} />

      <main>
        {!current ? (
          <div style={{ gridColumn: "1 / -1" }} className="empty-state">
            Pick a patient from the dropdown to begin. Tasks 1 &amp; 2 load instantly; the AI
            summary and chat use the Llama model and take longer.
          </div>
        ) : current.notInList ? (
          <div style={{ gridColumn: "1 / -1" }} className="empty-state">
            Patient "{current.id}" not found. Please select a valid patient from the dropdown.
          </div>
        ) : (
          <>
            <div style={{ gridColumn: "1 / -1" }}>
              <TodaySymptoms patientId={current.id} />
            </div>
            <VitalsTimeline key={`stream-${panelKey}`} patientId={current.id} />
            <RedFlagCurrent key={`t1-${panelKey}`} patientId={current.id} />
            <RedFlagML key={`t5-${panelKey}`} patientId={current.id} />
            <RedFlagDelta key={`t2-${panelKey}`} patientId={current.id} />
            <HistorySummary key={`t3-${panelKey}`} patientId={current.id} />
            <ChatPanel key={`t4-${current.id}`} patientId={current.id} />
            <VisitHistory key={`visits-${panelKey}`} patientId={current.id} />
          </>
        )}
      </main>
    </>
  );
}
