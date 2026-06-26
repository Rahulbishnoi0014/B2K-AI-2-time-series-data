"""
Task 4: Patient-Scoped RAG Chatbot
====================================
The doctor types a question; the chatbot answers using ONLY that patient's
data. Uses ChromaDB (vector database) + sentence-transformers for retrieval,
then the Kaggle-hosted Llama 3.1 8B for the answer.

WHY RAG INSTEAD OF JUST STUFFING ALL HISTORY INTO THE PROMPT?
For one patient with 5 visits it would work. But for a long-term patient
with 50+ visits, you'd exceed the model's context window. RAG retrieves
only the most relevant chunks, keeping prompts small and answers focused.

CRITICAL SAFETY DESIGN:
Every query is filtered by patient_id at the vector-store level.
The retriever CANNOT return chunks from other patients. This is enforced
in code, not just by prompt instruction.

HOW TO RUN:
  Step 1 (one-time): python task4_rag_chatbot.py --index
    This builds the vector index from your output/ JSON files.
  Step 2: python task4_rag_chatbot.py --chat <patient_id>
    Starts an interactive chat for that patient.
  Step 3 (optional): python task4_rag_chatbot.py --ask <patient_id> "<question>"
    One-shot question; useful for testing.

DEPENDENCIES:
  pip install chromadb sentence-transformers
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

try:
    import chromadb
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("ERROR: missing dependencies. Install with:")
    print("  pip install chromadb sentence-transformers")
    raise SystemExit(1)

from kaggle_ollama_client import chat, check_connection
from task3_summarize_history import load_patient_history


# =========================
# CONFIG
# =========================
CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "patient_records"
EMBED_MODEL = "all-MiniLM-L6-v2"
TOP_K = 6  # How many chunks to retrieve per query

# Lazy-load the embedder (it downloads ~90MB the first time)
_embedder = None
def get_embedder():
    global _embedder
    if _embedder is None:
        print(f"Loading embedding model ({EMBED_MODEL})...")
        _embedder = SentenceTransformer(EMBED_MODEL)
    return _embedder


def get_collection():
    """Get (or create) the ChromaDB collection."""
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


# =========================
# INDEXING
# =========================

def build_chunks_for_patient(patient_history):
    """
    Turn one patient's full history into a list of chunks suitable for embedding.
    Each chunk is one visit, formatted as natural language so semantic search works well.
    """
    chunks = []

    for i, visit in enumerate(patient_history["visits"], 1):
        try:
            visit_date = datetime.fromisoformat(visit["date"]).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            visit_date = visit["date"]

        lines = [f"Visit on {visit_date} (visit #{i} of {patient_history['total_visits']})"]
        if visit["symptoms"]:
            lines.append(f"Patient presented with: {', '.join(visit['symptoms'])}.")
        if visit["diagnoses"]:
            lines.append(f"Diagnoses recorded: {', '.join(visit['diagnoses'])}.")
        if visit["tests_ordered"]:
            lines.append(f"Tests ordered: {', '.join(visit['tests_ordered'])}.")
        if visit["prescribed_drugs"]:
            drug_descriptions = [
                f"{d['name']} {d['dose']} ({d['timings']}, {d['duration']})"
                for d in visit["prescribed_drugs"]
            ]
            lines.append(f"Medications prescribed: {'; '.join(drug_descriptions)}.")

        chunk_text = " ".join(lines)
        chunks.append({
            "text": chunk_text,
            "visit_date": visit_date,
            "visit_number": i,
        })

    # Also add a profile chunk for general questions
    profile = (
        f"Patient {patient_history['name']} is {patient_history['gender']}, "
        f"date of birth {patient_history['age_dob']}, blood group {patient_history['bloodgroup']}. "
        f"Allergies: {patient_history['allergies'] or 'none recorded'}. "
        f"Has {patient_history['total_visits']} visit(s) on file."
    )
    chunks.append({
        "text": profile,
        "visit_date": "profile",
        "visit_number": 0,
    })

    return chunks


def index_all_patients(data_dir="output"):
    """Build the vector index for all patients in the dataset."""
    print(f"Building vector index from {data_dir}/ ...")

    from db import load_collection
    users = load_collection("users")
    patients = [u for u in users if u.get("type") == "patient"]
    print(f"  Found {len(patients)} patients")

    embedder = get_embedder()
    collection = get_collection()

    # Wipe existing index for a clean rebuild
    try:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = get_collection()

    all_documents = []
    all_metadatas = []
    all_ids = []

    indexed_patients = 0
    skipped = 0

    for i, patient in enumerate(patients):
        if (i + 1) % 50 == 0:
            print(f"  Processed {i+1}/{len(patients)} patients...")

        history = load_patient_history(patient["_id"], data_dir)
        if not history or not history["visits"]:
            skipped += 1
            continue

        chunks = build_chunks_for_patient(history)
        for j, chunk in enumerate(chunks):
            chunk_id = f"{patient['_id']}_chunk_{j}"
            all_documents.append(chunk["text"])
            all_metadatas.append({
                "patient_id": patient["_id"],
                "patient_name": history["name"],
                "visit_date": chunk["visit_date"],
                "visit_number": chunk["visit_number"],
            })
            all_ids.append(chunk_id)
        indexed_patients += 1

    if not all_documents:
        print("ERROR: No documents to index. Make sure synthetic data exists.")
        return

    print(f"  Embedding {len(all_documents)} chunks... (this takes ~1-2 minutes)")
    # Batch embeddings to avoid memory spikes
    BATCH = 100
    for i in range(0, len(all_documents), BATCH):
        batch_docs = all_documents[i:i + BATCH]
        batch_meta = all_metadatas[i:i + BATCH]
        batch_ids = all_ids[i:i + BATCH]
        embeddings = embedder.encode(batch_docs, show_progress_bar=False).tolist()
        collection.add(
            documents=batch_docs,
            metadatas=batch_meta,
            ids=batch_ids,
            embeddings=embeddings,
        )

    print(f"\n✓ Indexed {indexed_patients} patients, {len(all_documents)} total chunks")
    print(f"  Skipped (no visits): {skipped}")
    print(f"  Index stored in: {Path(CHROMA_DIR).absolute()}")


# =========================
# RETRIEVAL
# =========================

def retrieve_for_patient(patient_id, question, top_k=TOP_K):
    """
    Retrieve the top-k most relevant chunks from THIS PATIENT ONLY.
    The where={'patient_id': patient_id} filter is the safety boundary —
    no other patient's data can leak in.
    """
    embedder = get_embedder()
    collection = get_collection()

    query_embedding = embedder.encode([question]).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k,
        where={"patient_id": patient_id},  # CRITICAL: enforces patient scope
    )

    if not results["documents"] or not results["documents"][0]:
        return []

    # Sort retrieved chunks by visit date if available (older first for narrative flow)
    chunks_with_meta = list(zip(results["documents"][0], results["metadatas"][0]))
    chunks_with_meta.sort(key=lambda x: x[1].get("visit_date", ""))

    return chunks_with_meta


# =========================
# CHATBOT
# =========================

SYSTEM_PROMPT_RAG = """You are a clinical assistant answering a doctor's questions about a specific patient.

STRICT RULES:
- Use ONLY the patient records provided in each message. Never use outside knowledge about medications, dosing, or guidelines beyond what's in the records.
- If the answer is not in the records, respond exactly: "I don't have that information in the patient's records."
- Be concise. 1-3 sentences usually. Don't repeat the records verbatim — answer the question.
- If asked to compare or trend over time, walk through the relevant visits chronologically.
- Never invent medications, dosages, or test results."""


def build_messages(patient_id, question, conversation_history=None):
    """Construct the message list for the LLM, including retrieved context."""
    chunks = retrieve_for_patient(patient_id, question)

    if not chunks:
        context = "(No records found for this patient.)"
        patient_name = "(unknown)"
    else:
        context_lines = []
        patient_name = chunks[0][1].get("patient_name", "(unknown)")
        for doc, meta in chunks:
            context_lines.append(f"[{meta.get('visit_date', '?')}] {doc}")
        context = "\n".join(context_lines)

    messages = [{"role": "system", "content": SYSTEM_PROMPT_RAG}]

    # Add prior conversation turns if any
    if conversation_history:
        messages.extend(conversation_history)

    # Wrap the question with the retrieved context
    user_content = (
        f"Patient: {patient_name}\n\n"
        f"Relevant records:\n{context}\n\n"
        f"Doctor's question: {question}"
    )
    messages.append({"role": "user", "content": user_content})

    return messages, patient_name


def ask(patient_id, question, conversation_history=None):
    """One-shot Q&A. Returns the answer string and the updated history."""
    messages, patient_name = build_messages(patient_id, question, conversation_history)
    answer = chat(messages, max_tokens=300, temperature=0.1)

    # Append this turn to history (for multi-turn chats)
    new_history = (conversation_history or []) + [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ]
    return answer, new_history, patient_name


def interactive_chat(patient_id):
    """Multi-turn chat loop in the terminal."""
    history = load_patient_history(patient_id)
    if not history:
        print(f"ERROR: Patient {patient_id} not found.")
        return

    print("=" * 60)
    print(f"Chatting about: {history['name']}")
    print(f"  Visits on record: {history['total_visits']}")
    print(f"  Allergies: {history['allergies'] or 'none recorded'}")
    print("=" * 60)
    print("Type your questions. Type 'exit' or 'quit' to leave.\n")

    conversation = []
    while True:
        try:
            question = input("Doctor> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit", "bye"):
            print("Exiting chat.")
            break

        print("(thinking...)")
        try:
            answer, conversation, _ = ask(patient_id, question, conversation)
            print(f"\nAssistant: {answer}\n")
        except Exception as e:
            print(f"\nError: {e}\n")


# =========================
# CLI
# =========================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task 4: Patient RAG Chatbot")
    parser.add_argument("--index", action="store_true",
                        help="Build (or rebuild) the vector index")
    parser.add_argument("--chat", metavar="PATIENT_ID",
                        help="Start interactive chat for this patient")
    parser.add_argument("--ask", nargs=2, metavar=("PATIENT_ID", "QUESTION"),
                        help="Ask one question and print the answer")
    args = parser.parse_args()

    if args.index:
        index_all_patients()
    elif args.chat:
        if not check_connection():
            raise SystemExit(1)
        interactive_chat(args.chat)
    elif args.ask:
        if not check_connection():
            raise SystemExit(1)
        patient_id, question = args.ask
        answer, _, name = ask(patient_id, question)
        print(f"\nPatient: {name}")
        print(f"Question: {question}")
        print(f"\nAnswer: {answer}")
    else:
        parser.print_help()
        print("\nQuick start:")
        print("  python task4_rag_chatbot.py --index")
        print("  python task4_rag_chatbot.py --chat <patient_id>")
