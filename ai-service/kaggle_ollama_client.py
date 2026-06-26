"""
Local Client for Kaggle-Hosted Ollama
======================================
Use this on your laptop to verify your Kaggle Ollama tunnel is working,
and as the foundation for Tasks 3 and 4 of the tele-consultation system.

HOW TO USE:
1. Make sure the Kaggle notebook is running and showing a tunnel URL.
2. Copy that URL (looks like https://xyz-12345.ngrok-free.app)
3. Open this file and paste it into OLLAMA_URL below.
4. Run:  python kaggle_ollama_client.py
5. If you see a medical response printed, you're good.

IMPORTANT NOTES ABOUT ngrok:
- Free ngrok adds an interstitial warning page on the first browser visit.
  This is bypassed for API calls by setting the 'ngrok-skip-browser-warning' header
  (already handled below).
- Free ngrok tunnels disconnect after ~2 hours of inactivity. If calls start failing,
  restart the Kaggle notebook from Cell 5 to get a fresh tunnel.
"""

import requests
import json
import time

# =========================
# CONFIG — UPDATE THIS!
# =========================
# Paste the ngrok URL from Cell 5 of your Kaggle notebook here.
# Include https:// but no trailing slash.
import os
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")

# Required header to bypass ngrok's free-tier browser warning page
HEADERS = {
    "Content-Type": "application/json",
    "ngrok-skip-browser-warning": "true",
}

# Some networks (e.g. an institute Wi-Fi) configure a system-wide HTTP proxy
# that `requests` picks up even for localhost -- bypass it explicitly so a
# local Ollama is always reachable regardless of system network settings.
NO_PROXY = {"http": None, "https": None}

# =========================
# HELPER FUNCTIONS
# =========================

def check_connection():
    """Confirm Ollama is reachable through the tunnel."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", headers=HEADERS, timeout=10, proxies=NO_PROXY)
        if r.status_code == 200:
            models = r.json().get("models", [])
            print(f"✓ Connected. Models available on Kaggle: {[m['name'] for m in models]}")
            return True
        print(f"✗ Server responded with status {r.status_code}: {r.text[:200]}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"✗ Could not reach Ollama at {OLLAMA_URL}")
        print(f"  Error: {e}")
        print("  Check that:")
        print("  - The Kaggle notebook is still running")
        print("  - OLLAMA_URL above matches the URL from Cell 5 of the notebook")
        print("  - You have internet")
        return False


def generate(prompt, system=None, max_tokens=500, temperature=0.3):
    """
    Send a single prompt to the Kaggle-hosted Ollama and get back text.

    Args:
        prompt: The user's question or input text.
        system: Optional system message to set the AI's behavior.
        max_tokens: Cap on response length (keeps things fast).
        temperature: 0.0 = deterministic, 1.0 = creative.
                     Use 0.1-0.3 for medical/factual work.
    """
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if system:
        payload["system"] = system

    start = time.time()
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        headers=HEADERS,
        json=payload,
        timeout=300,  # LLM responses can take 30-90s through the tunnel
        proxies=NO_PROXY,
    )
    elapsed = time.time() - start

    if response.status_code != 200:
        raise RuntimeError(f"Ollama error {response.status_code}: {response.text[:300]}")

    result = response.json()
    return {
        "text": result.get("response", "").strip(),
        "elapsed_seconds": round(elapsed, 1),
        "tokens": result.get("eval_count", 0),
    }


def chat(messages, max_tokens=500, temperature=0.3):
    """
    Multi-turn chat. Useful for Task 4 (the doctor chatbot).

    Args:
        messages: List of {"role": "user"|"assistant"|"system", "content": "..."}
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        headers=HEADERS,
        json=payload,
        timeout=300,
        proxies=NO_PROXY,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Ollama error {response.status_code}: {response.text[:300]}")
    return response.json().get("message", {}).get("content", "").strip()


# =========================
# TESTS
# =========================

def test_basic():
    """Test 1: Simple completion."""
    print("\n--- Test 1: Basic medical question ---")
    result = generate("In one sentence, what does an elevated HbA1c indicate?")
    print(f"Response ({result['elapsed_seconds']}s, {result['tokens']} tokens):")
    print(f"  {result['text']}")


def test_summary_preview():
    """Test 2: Preview of what Task 3 will do — summarize a mock prescription history."""
    print("\n--- Test 2: Mock prescription summary (preview of Task 3) ---")

    mock_history = """
Patient: Mr. Ravi Kumar, Age 58, Male
Visit history (most recent first):

[2026-04-12] Diagnosis: Type 2 Diabetes, Hypertension
  Prescribed: Metformin 500mg twice daily, Telmisartan 40mg morning
  Tests ordered: HbA1c, Lipid Profile, KFT

[2026-01-08] Diagnosis: Type 2 Diabetes (newly diagnosed), Hypertension
  Prescribed: Metformin 500mg once daily, Amlodipine 5mg morning
  Tests ordered: Blood Sugar Fasting, HbA1c, ECG

[2025-09-22] Diagnosis: Hypertension
  Prescribed: Amlodipine 5mg morning
  Tests ordered: BP monitoring, ECG, Lipid Profile
"""

    system = (
        "You are a clinical assistant helping a doctor review a patient's history. "
        "Produce a brief, factual summary. Do not invent medications or tests not in the data. "
        "If something is unclear, say so."
    )
    prompt = (
        f"Summarize this patient's prescription and test history. "
        f"Highlight: (1) what they take currently, (2) what changed between visits, "
        f"(3) any recurring tests, (4) clinical trends worth noting.\n\n{mock_history}"
    )

    result = generate(prompt, system=system, max_tokens=400, temperature=0.2)
    print(f"Summary ({result['elapsed_seconds']}s):")
    print(result["text"])


def test_chat_preview():
    """Test 3: Preview of what Task 4 will do — answer a doctor's question."""
    print("\n--- Test 3: Mock doctor Q&A (preview of Task 4) ---")

    # In the real Task 4, these context chunks will come from a vector database
    # filtered by patient_id. For now they're hardcoded.
    patient_context = """
Patient records:
- 2026-04-12: Diagnosis Type 2 Diabetes + Hypertension. Prescribed Metformin 500mg BD, Telmisartan 40mg OD.
- 2026-01-08: Newly diagnosed T2DM. Started Metformin 500mg OD, continued Amlodipine 5mg.
- 2025-09-22: BP elevated. Started Amlodipine 5mg.
- HbA1c 2026-04: 8.2%. HbA1c 2026-01: 9.1%.
"""

    messages = [
        {
            "role": "system",
            "content": (
                "You answer a doctor's questions about a specific patient using ONLY "
                "the records provided. If the answer isn't in the records, say "
                "'I don't have that information in the records.' Do not speculate."
            ),
        },
        {
            "role": "user",
            "content": f"Here are the patient's records:\n{patient_context}\n\nDoctor's question: How has the patient's HbA1c trended over the recent visits?",
        },
    ]

    response = chat(messages, max_tokens=200, temperature=0.1)
    print(f"AI response to doctor:")
    print(f"  {response}")


# =========================
# MAIN
# =========================

if __name__ == "__main__":
    print("=" * 60)
    print("Kaggle Ollama Tunnel Verification")
    print("=" * 60)

    if OLLAMA_URL == "https://YOUR-NGROK-URL.ngrok-free.app":
        print("\n⚠️  You haven't set OLLAMA_URL yet.")
        print("   Open this file and paste your Kaggle ngrok URL at the top.")
        raise SystemExit(1)

    if not check_connection():
        raise SystemExit(1)

    try:
        test_basic()
        test_summary_preview()
        test_chat_preview()
        print("\n" + "=" * 60)
        print("✓ All tests passed. Your Kaggle Ollama setup is working.")
        print("=" * 60)
        print("\nWhat this means:")
        print("  - You can now build Task 3 (summary) and Task 4 (chatbot)")
        print("  - The functions `generate()` and `chat()` above are reusable")
        print("    Just import them: from kaggle_ollama_client import generate, chat")
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        print("\nCommon causes:")
        print("  - Kaggle notebook stopped running")
        print("  - ngrok tunnel timed out (free tier: 2 hours of inactivity)")
        print("  - Model didn't finish loading yet (re-run after a minute)")
        raise SystemExit(1)
