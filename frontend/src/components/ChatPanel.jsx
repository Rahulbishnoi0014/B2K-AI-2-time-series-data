import { useEffect, useRef, useState } from "react";
import { chatAsk } from "../api/client.js";

const SUGGESTIONS = [
  "What medications is this patient currently on?",
  "How has their blood pressure trended?",
  "Any recurring tests ordered?",
  "Summarize the most recent visit.",
];

export default function ChatPanel({ patientId }) {
  const [messages, setMessages] = useState([]); // {role, text}
  const [history, setHistory] = useState([]); // raw conversation_history for the API
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);

  // Reset when patient changes
  useEffect(() => {
    setMessages([]);
    setHistory([]);
    setInput("");
  }, [patientId]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  async function send(question) {
    const q = (question ?? input).trim();
    if (!q || busy || !patientId) return;

    setMessages((m) => [...m, { role: "user", text: q }]);
    setInput("");
    setBusy(true);

    try {
      const data = await chatAsk(patientId, q, history);
      setMessages((m) => [...m, { role: "assistant", text: data.answer }]);
      setHistory(data.conversation_history || []);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: "❌ Error: " + e.message }]);
    } finally {
      setBusy(false);
    }
  }

  const disabled = !patientId;

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Ask About This Patient</h2>
        <span className="tag">Task 4 · RAG chat</span>
      </div>
      <div className="panel-body">
        <div className="chat-messages" ref={scrollRef}>
          {messages.length === 0 && !busy && (
            <div className="empty-state">Ask a question about this patient.</div>
          )}
          {messages.map((m, i) => (
            <div className={`msg ${m.role}`} key={i}>
              {m.text}
            </div>
          ))}
          {busy && <div className="msg thinking">AI is thinking…</div>}
        </div>

        {!disabled && (
          <div className="chat-suggestions">
            {SUGGESTIONS.map((s) => (
              <span className="chip" key={s} onClick={() => send(s)}>
                {s}
              </span>
            ))}
          </div>
        )}

        <div className="chat-input-row">
          <input
            value={input}
            disabled={disabled || busy}
            placeholder={disabled ? "Select a patient first" : "Type a question…"}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
          />
          <button className="btn" disabled={disabled || busy} onClick={() => send()}>
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
