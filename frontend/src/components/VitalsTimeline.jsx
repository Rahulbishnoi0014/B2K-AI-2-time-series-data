import { useEffect, useRef, useState } from "react";
import { vitalsLiveUrl } from "../api/client.js";

// normal ranges mirror VITAL_PROFILES / BP_PROFILES in generate_synthetic_data.py
const VITAL_META = {
  temperature: { label: "Temp", unit: "°F", normalRange: [97.0, 99.0] },
  blood_oxygen: { label: "SpO2", unit: "%", normalRange: [96, 100] },
  blood_glucose: { label: "Glucose", unit: "mg/dL", normalRange: [75, 135] },
  spirometer: { label: "Peak Flow", unit: "L/min", normalRange: [380, 600] },
  blood_pressure: {
    label: "BP (systolic/diastolic)",
    unit: "mmHg",
    normalRange: [105, 125],
    normalRangeSecondary: [65, 82],
  },
};

const RISK_PILL = { low: "NORMAL", medium: "HIGH", high: "CRITICAL" };
const GOOD_COLOR = "#2e7d4f";
const BAD_COLOR = "#c0392b";
const GLITCH_COLOR = "#9aa0a6";

function fmtTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function pointColor(value, quality, normalRange) {
  if (quality === "garbled" || value == null) return GLITCH_COLOR;
  const [lo, hi] = normalRange;
  return value < lo || value > hi ? BAD_COLOR : GOOD_COLOR;
}

// Chart x-axis is TIME-based (fraction of episode duration), not index-based.
// That's what makes live mode work: a new point appears at its correct fixed
// position instead of every existing point shifting as more data arrives.
function VitalChart({ points, episodeStartMs, episodeEndMs, normalRange, normalRangeSecondary, width = 320, height = 90 }) {
  const padX = 6;
  const padY = 10;
  const axisH = 16;
  const plotH = height - axisH;
  const durationMs = Math.max(1, episodeEndMs - episodeStartMs);

  const primaryVals = points.map((p) => (p.v ?? p.systolic));
  const secondaryVals = normalRangeSecondary ? points.map((p) => p.diastolic) : [];
  const allVals = [...primaryVals, ...secondaryVals, ...normalRange, ...(normalRangeSecondary || [])].filter(
    (v) => v != null
  );

  if (points.length === 0) {
    return <div className="empty-state">Waiting for readings…</div>;
  }

  const min = Math.min(...allVals);
  const max = Math.max(...allVals);
  const span = max - min || 1;

  const xOf = (t) => {
    const frac = Math.min(1, Math.max(0, (new Date(t).getTime() - episodeStartMs) / durationMs));
    return padX + frac * (width - 2 * padX);
  };
  const yOf = (v) => plotH - padY - ((v - min) / span) * (plotH - 2 * padY);

  const linePath = (vals) =>
    points
      .map((p, i) => (vals[i] == null ? null : `${i === 0 ? "M" : "L"}${xOf(p.t).toFixed(1)},${yOf(vals[i]).toFixed(1)}`))
      .filter(Boolean)
      .join(" ");

  const bandRect = (range, fill) => {
    const [lo, hi] = range;
    const y1 = yOf(Math.min(hi, max));
    const y2 = yOf(Math.max(lo, min));
    return <rect x={padX} y={y1} width={width - 2 * padX} height={Math.max(1, y2 - y1)} fill={fill} />;
  };

  const lastT = points[points.length - 1].t;

  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      {bandRect(normalRange, "rgba(46,125,79,0.10)")}
      {normalRangeSecondary && bandRect(normalRangeSecondary, "rgba(46,125,79,0.06)")}

      {secondaryVals.length > 0 && (
        <path d={linePath(secondaryVals)} fill="none" stroke="#b8b8b8" strokeWidth="1" strokeDasharray="3,3" />
      )}
      <path d={linePath(primaryVals)} fill="none" stroke="#cfcfcf" strokeWidth="1.25" />

      {primaryVals.map((v, i) =>
        v == null ? null : (
          <circle
            key={i}
            cx={xOf(points[i].t)}
            cy={yOf(v)}
            r={points[i].quality === "garbled" ? 2 : 2.4}
            fill={pointColor(v, points[i].quality, normalRange)}
            opacity={points[i].quality === "garbled" ? 0.6 : 1}
          />
        )
      )}

      {/* live cursor at the most recent reading */}
      <circle cx={xOf(lastT)} cy={2} r={2.5} fill="#1f7a8c" />

      <line x1={padX} y1={plotH} x2={width - padX} y2={plotH} stroke="var(--line)" strokeWidth="1" />
      <text x={padX} y={height - 3} fontSize="9" fill="var(--ink-soft)">
        {fmtTime(points[0]?.t)}
      </text>
      <text x={width - padX} y={height - 3} fontSize="9" fill="var(--ink-soft)" textAnchor="end">
        {fmtTime(lastT)}
      </text>
    </svg>
  );
}

function VitalRow({ vitalKey, points, episodeStartMs, episodeEndMs }) {
  const meta = VITAL_META[vitalKey] || { label: vitalKey, unit: "", normalRange: [0, 0] };
  const goodCount = points.filter((p) => p.quality !== "garbled").length;

  let latestText;
  if (vitalKey === "blood_pressure") {
    const last = points[points.length - 1];
    latestText = last ? `${last.systolic}/${last.diastolic}` : "—";
  } else {
    const last = points[points.length - 1];
    latestText = last && last.v != null ? `${Math.round(last.v * 10) / 10}` : "—";
  }

  const outOfRangeCount = points.filter((p) => {
    if (p.quality === "garbled") return false;
    const v = p.v ?? p.systolic;
    return v != null && (v < meta.normalRange[0] || v > meta.normalRange[1]);
  }).length;

  return (
    <div className="vital-stream-row">
      <div className="vital-stream-info">
        <div className="vital-stream-label">{meta.label}</div>
        <div className="vital-stream-value">
          {latestText} <span className="vital-stream-unit">{meta.unit}</span>
        </div>
        <div className="vital-stream-meta">
          {points.length} readings ({goodCount} good)
          {outOfRangeCount > 0 ? (
            <span style={{ color: BAD_COLOR }}> · {outOfRangeCount} out of normal range</span>
          ) : (
            <span style={{ color: GOOD_COLOR }}> · stayed in normal range</span>
          )}
        </div>
      </div>
      <VitalChart
        points={points}
        episodeStartMs={episodeStartMs}
        episodeEndMs={episodeEndMs}
        normalRange={meta.normalRange}
        normalRangeSecondary={meta.normalRangeSecondary}
      />
    </div>
  );
}

function Legend() {
  return (
    <div style={{ display: "flex", gap: 14, fontSize: 11, color: "var(--ink-soft)", marginBottom: 10, flexWrap: "wrap" }}>
      <span>
        <span style={{ color: GOOD_COLOR }}>●</span> normal
      </span>
      <span>
        <span style={{ color: BAD_COLOR }}>●</span> out of range
      </span>
      <span>
        <span style={{ color: GLITCH_COLOR }}>●</span> sensor glitch (excluded from scoring)
      </span>
      <span>shaded band = normal range</span>
    </div>
  );
}

const VITAL_ORDER = ["temperature", "blood_oxygen", "blood_pressure", "blood_glucose", "spirometer"];

export default function VitalsTimeline({ patientId }) {
  // status: idle | connecting | streaming | done | error
  const [status, setStatus] = useState("idle");
  const [meta, setMeta] = useState(null);
  const [vitalsData, setVitalsData] = useState({});
  const esRef = useRef(null);
  const gotStartRef = useRef(false);

  function startStream() {
    if (esRef.current) esRef.current.close();
    if (!patientId) return;

    setStatus("connecting");
    setMeta(null);
    setVitalsData({});
    gotStartRef.current = false;

    const es = new EventSource(vitalsLiveUrl(patientId));
    esRef.current = es;

    es.addEventListener("start", (e) => {
      gotStartRef.current = true;
      setMeta(JSON.parse(e.data));
      setStatus("streaming");
    });

    es.addEventListener("reading", (e) => {
      const ev = JSON.parse(e.data);
      setVitalsData((prev) => ({ ...prev, [ev.vital]: [...(prev[ev.vital] || []), ev] }));
    });

    es.addEventListener("done", () => {
      setStatus("done");
      es.close();
    });

    es.onerror = () => {
      setStatus(gotStartRef.current ? "done" : "error");
      es.close();
    };
  }

  useEffect(() => {
    startStream();
    return () => esRef.current?.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId]);

  const ews = meta?.ews || {};
  const sevClass = RISK_PILL[ews.risk_level] || "NORMAL";
  const episodeStartMs = meta ? new Date(meta.episode_start).getTime() : 0;
  const episodeEndMs = meta ? new Date(meta.episode_end).getTime() : 0;

  return (
    <div className="panel" style={{ gridColumn: "1 / -1" }}>
      <div className="panel-head">
        <h2>Vitals Stream — Latest Monitoring Episode</h2>
        <span className="tag">
          {status === "streaming" ? "● LIVE — replaying device readings" : "Device readings over the visit"}
        </span>
      </div>
      <div className="panel-body">
        {status === "idle" || status === "connecting" ? (
          <div className="loading">
            <div className="spinner" /> Connecting to live feed…
          </div>
        ) : status === "error" ? (
          <div className="empty-state">No vitals on record for this patient.</div>
        ) : (
          <>
            <div style={{ marginBottom: 8, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span className={`sev-pill ${sevClass}`}>{(ews.risk_level || "low").toUpperCase()}</span>
              <span style={{ fontSize: 12, color: "var(--ink-soft)" }}>
                {meta?.duration_hours}h episode compressed into ~{Math.round((meta?.playback_ms || 0) / 1000)}s ·
                EWS max {ews.max_score ?? "—"}, current {ews.final_score ?? "—"}
                {ews.single_param_red_flag ? " · single-parameter red flag" : ""}
              </span>
              {status === "done" && (
                <button className="btn secondary" onClick={startStream} style={{ marginLeft: "auto" }}>
                  ▶ Replay
                </button>
              )}
            </div>
            <Legend />
            <div className="vital-stream-grid">
              {VITAL_ORDER.map((key) => (
                <VitalRow
                  key={key}
                  vitalKey={key}
                  points={vitalsData[key] || []}
                  episodeStartMs={episodeStartMs}
                  episodeEndMs={episodeEndMs}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
