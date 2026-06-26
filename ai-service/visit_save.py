"""
Reindex Module
==============
After Node writes a new visit to MongoDB, it calls Python to refresh that
ONE patient's vectors in ChromaDB so Task 4 (RAG chat) sees the new visit
immediately.

WHY THIS LIVES IN PYTHON:
ChromaDB and sentence-transformers are Python libraries. Node owns all the
durable data writes (Mongo), but the vector index derived from that data
must be rebuilt here. This is the single, clean seam between the two
backends.

The actual visit-save logic (consultations, patient_details, drugs, vitals,
master upserts) now lives in node-backend/src/routes/visits.js.
"""


def reindex_patient(real_patient_id, data_dir=None):
    """
    Re-embed a single patient into ChromaDB after a visit is saved.
    Reads the patient's full history via the db.py shim (Mongo OR JSON files,
    depending on USE_MONGO), rebuilds their chunks, deletes their old vectors,
    and re-adds fresh ones.
    Returns True on success, False on failure (logged, never raised).

    In JSON mode load_patient_history reads through db.load_collection, which
    uses the shared DATA_DIR env var — so data_dir is only a harmless fallback.
    """
    import os
    try:
        from task4_rag_chatbot import (
            get_embedder, get_collection, build_chunks_for_patient
        )
        from task3_summarize_history import load_patient_history

        history = load_patient_history(
            real_patient_id, data_dir or os.environ.get("DATA_DIR", "output")
        )
        if not history or not history["visits"]:
            return False

        embedder = get_embedder()
        collection = get_collection()

        # Drop this patient's existing chunks so we don't duplicate
        try:
            collection.delete(where={"patient_id": real_patient_id})
        except Exception:
            pass

        chunks = build_chunks_for_patient(history)
        documents, metadatas, ids = [], [], []
        for j, chunk in enumerate(chunks):
            documents.append(chunk["text"])
            metadatas.append({
                "patient_id": real_patient_id,
                "patient_name": history["name"],
                "visit_date": chunk["visit_date"],
                "visit_number": chunk["visit_number"],
            })
            ids.append(f"{real_patient_id}_chunk_{j}")

        if documents:
            embeddings = embedder.encode(documents, show_progress_bar=False).tolist()
            collection.add(documents=documents, metadatas=metadatas, ids=ids, embeddings=embeddings)
        return True

    except Exception as e:
        print(f"[reindex_patient] Failed: {e}")
        return False
