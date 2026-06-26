# Tele-Consultation AI

A doctor's console for synthetic patient data, combining four AI features:

1. **Red-flag current vitals** (rules engine, no LLM)
2. **Cross-visit vitals deltas** (rules engine, no LLM)
3. **AI history summary** (Llama 3.1 8B, runs locally via Ollama)
4. **Patient-scoped RAG chat** (ChromaDB + embeddings + Llama)

## Stack

| Layer | Tech | Responsibility |
|-------|------|----------------|
| Frontend | **React** (Vite) | Doctor console UI |
| Gateway | **Node.js** (Express) | All data reads/writes, friendly IDs, proxies AI calls |
| AI service | **Python** (FastAPI) | The four AI tasks + ChromaDB reindex — unchanged logic |
| Storage | **JSON files** (default) or **MongoDB** | All patient/clinical data |
| LLM | Llama 3.1 8B via **local Ollama** | Runs on the same machine as the Python service |

**Rule of thumb:** Node owns the data. Python owns AI inference. The browser only ever talks to Node.

```
React ──► Node (Express, :8000) ──► Storage (JSON files or MongoDB)
                  │
                  └──► Python AI service (:8001) ──► local Ollama / ChromaDB
```

## Storage: one flag switches everything

Both backends read the same `USE_MONGO` flag, so you flip the whole system at once.

- `USE_MONGO=false` **(default)** — Node and Python share local `output/*.json` files. No database to install.
- `USE_MONGO=true` — both use MongoDB at `MONGO_URI`.

In JSON mode, `DATA_DIR` must point to the **same folder** on both services (defaults already align: the Node backend points at `../ai-service/output`).

## One-time setup

### 1. Install and run Ollama locally (no Kaggle, no ngrok)
```bash
# Install: https://ollama.com/download   (or: curl -fsSL https://ollama.com/install.sh | sh)
ollama serve            # runs on http://localhost:11434
ollama pull llama3.2:3b # ~2 GB, one time
```
The default `OLLAMA_URL=http://localhost:11434` already points here — no change needed.
When you later host this on a server, run Ollama on that server the same way; it stays local to wherever the Python service runs.

### 2. Generate the synthetic data
```bash
cd data-seed
pip install faker
python generate_synthetic_data.py   # writes output/*.json
# Move/point the data where both backends expect it:
mv output ../ai-service/output       # JSON mode default location
```
(If you set `USE_MONGO=true` later, set `LOAD_TO_MONGO = True` in the generator instead and it loads straight into Mongo.)

### 3. Build the ChromaDB vector index (for Task 4 chat)
```bash
cd ai-service
pip install -r requirements.txt
cp .env.example .env          # USE_MONGO=false, DATA_DIR=output, OLLAMA_MODEL=llama3.2:3b
python task4_rag_chatbot.py --index
```
`.env` is loaded automatically (via `python-dotenv`) by every script in this folder — no need to `$env:` export anything by hand.

## Running (local, three terminals)

**Terminal 1 — Python AI service**
```bash
cd ai-service
cp .env.example .env          # if you haven't already (see step 3 above)
uvicorn ai_api:app --host 0.0.0.0 --port 8001
```

**Terminal 2 — Node gateway**
```bash
cd node-backend
npm install
cp .env.example .env          # USE_MONGO=false, DATA_DIR=../ai-service/output
npm start
```

**Terminal 3 — React**
```bash
cd frontend
npm install
npm run dev                   # dev server on :5173, proxies /api to :8000
#   — or —
npm run build                 # then open http://localhost:8000 (Node serves dist/)
```

Open **http://localhost:8000** (or :5173 in dev). Pick a patient — Tasks 1 & 2 load instantly; Task 3 and Task 4 use the local Llama model (speed depends on your hardware/GPU).

## Switching to MongoDB later

1. Start Mongo (`docker run -d -p 27017:27017 mongo:7`).
2. In the generator set `LOAD_TO_MONGO = True`, run it once.
3. Set `USE_MONGO=true` in **both** `.env` files (node-backend and ai-service).
4. Re-run `python task4_rag_chatbot.py --index` (now reads from Mongo).
5. Restart both services. No code changes.

## Hosting on a server

Same as local — the LLM runs on the server via Ollama, not Kaggle.
- Run `ollama serve` + `ollama pull llama3.2:3b` on the server.
- Build the React bundle (`npm run build`) and let Node serve it.
- Point any public tunnel/reverse-proxy at the Node gateway (:8000). Keep the Python service (:8001) internal.

## What changed from the original single-file version

- `api_server.py` split into **Node routes** (data, friendly IDs, visit save) + **`ai_api.py`** (AI only).
- `gui.html` rebuilt as **React components** — same API calls, same behavior.
- `output/*.json` reads now go through a **storage layer** that switches between JSON files and MongoDB on one flag (`db.py` in Python, `db.js`/`jsonStore.js` in Node). Task logic is otherwise untouched.
- `visit_save.py` write logic ported to **`node-backend/src/routes/visits.js`**; only `reindex_patient` remains in Python (it needs ChromaDB).
- LLM access moved from Kaggle+ngrok to **local Ollama** — just an `OLLAMA_URL` pointing at `localhost:11434`. No code change; the client already reads it from env.
- The four AI task files changed in **~2 lines total** (the data-read swap). All thresholds, parsing, RAG retrieval, and the hallucination guard are unchanged.
