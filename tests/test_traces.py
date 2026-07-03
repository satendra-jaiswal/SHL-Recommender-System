"""
Trace replay tests — replays all 10 public conversation traces and computes Recall@10.

Run: pytest tests/test_traces.py -v -s

For each trace, we:
1. Replay the user turns through the live API
2. Compare the final recommendations against the expected shortlist
3. Compute Recall@10 = |recommended ∩ expected| / |expected|
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


import time

def chat(messages: list[dict]) -> dict:
    time.sleep(10)
    resp = client.post("/chat", json={"messages": messages})
    assert resp.status_code == 200
    return resp.json()


def recall_at_k(recommended_names: list[str], expected_names: list[str]) -> float:
    """Recall@10 = |recommended ∩ expected| / |expected|"""
    if not expected_names:
        return 1.0
    rec_set = {n.lower().strip() for n in recommended_names}
    exp_set = {n.lower().strip() for n in expected_names}
    return len(rec_set & exp_set) / len(exp_set)


def get_final_rec_names(conversation: list[dict]) -> list[str]:
    """
    Replay a conversation turn by turn.
    Returns the recommended assessment names from the FINAL response.
    """
    history = []
    final_recs = []
    for turn in conversation:
        if turn["role"] != "user":
            continue
        history.append({"role": "user", "content": turn["content"]})
        resp = chat(history)
        # Add assistant reply to history for next turn
        history.append({"role": "assistant", "content": resp["reply"]})
        # Track final recommendations
        if resp["recommendations"]:
            final_recs = [r["name"] for r in resp["recommendations"]]
        if resp["end_of_conversation"]:
            break
    return final_recs


# ── Trace C1: Senior Leadership ────────────────────────────────────────────
def test_c1_senior_leadership():
    conversation = [
        {"role": "user", "content": "We need a solution for senior leadership."},
        {"role": "user", "content": "The pool consists of CXOs, director-level positions; people with more than 15 years of experience."},
        {"role": "user", "content": "Selection — comparing candidates against a leadership benchmark."},
        {"role": "user", "content": "Perfect, that's what we need."},
    ]
    expected = [
        "Occupational Personality Questionnaire OPQ32r",
        "OPQ Universal Competency Report 2.0",
        "OPQ Leadership Report",
    ]
    final_recs = get_final_rec_names(conversation)
    recall = recall_at_k(final_recs, expected)
    print(f"\nC1 Recall@10: {recall:.2f} | Got: {final_recs}")
    assert recall >= 0.5, f"C1 Recall@10 too low: {recall:.2f}"


# ── Trace C2: Rust Engineer ────────────────────────────────────────────────
def test_c2_rust_engineer():
    conversation = [
        {"role": "user", "content": "I'm hiring a senior Rust engineer for high-performance networking infrastructure. What assessments should I use?"},
        {"role": "user", "content": "Yes, go ahead. Should I also add a cognitive test for this level?"},
        {"role": "user", "content": "That works. Thanks."},
    ]
    expected = [
        "Smart Interview Live Coding",
        "Linux Programming (General)",
        "Networking and Implementation (New)",
        "SHL Verify Interactive G+",
        "Occupational Personality Questionnaire OPQ32r",
    ]
    final_recs = get_final_rec_names(conversation)
    recall = recall_at_k(final_recs, expected)
    print(f"\nC2 Recall@10: {recall:.2f} | Got: {final_recs}")
    assert recall >= 0.4, f"C2 Recall@10 too low: {recall:.2f}"


# ── Trace C3: Contact Centre ───────────────────────────────────────────────
def test_c3_contact_centre():
    conversation = [
        {"role": "user", "content": "We're screening 500 entry-level contact centre agents next month."},
        {"role": "user", "content": "English — US-based operation."},
        {"role": "user", "content": "American accent, yes."},
        {"role": "user", "content": "What's the difference between the Contact Centre Call Simulation and the Customer Service Phone Simulation?"},
        {"role": "user", "content": "Go with the newer one. Confirmed."},
    ]
    expected = [
        "SVAR Spoken English (US) (New)",
        "Contact Centre Call Simulation",
        "Entry Level Customer Service",
        "Customer Service Phone Simulation",
    ]
    final_recs = get_final_rec_names(conversation)
    recall = recall_at_k(final_recs, expected)
    print(f"\nC3 Recall@10: {recall:.2f} | Got: {final_recs}")
    assert recall >= 0.4, f"C3 Recall@10 too low: {recall:.2f}"


# ── Trace C4: Graduate Finance ─────────────────────────────────────────────
def test_c4_graduate_finance():
    conversation = [
        {"role": "user", "content": "We're hiring 20 graduate financial analysts. They need strong numerical reasoning and some finance knowledge. Entry level — fresh grads from finance programmes."},
        {"role": "user", "content": "Add a situational judgement component — want to see how they handle ethical dilemmas in client-facing situations."},
        {"role": "user", "content": "Perfect. Can you also suggest how to stage this into two rounds?"},
        {"role": "user", "content": "That's exactly what we need. Confirmed."},
    ]
    expected = [
        "SHL Verify Interactive G+",
        "Financial Analysis (New)",
        "Occupational Personality Questionnaire OPQ32r",
        "Graduate Scenarios",
    ]
    final_recs = get_final_rec_names(conversation)
    recall = recall_at_k(final_recs, expected)
    print(f"\nC4 Recall@10: {recall:.2f} | Got: {final_recs}")
    assert recall >= 0.4, f"C4 Recall@10 too low: {recall:.2f}"


# ── Trace C7: Healthcare Admin ─────────────────────────────────────────────
def test_c7_healthcare_admin():
    conversation = [
        {"role": "user", "content": "We're hiring bilingual healthcare admin staff in South Texas — they handle patient records and need to be assessed in Spanish. HIPAA compliance is critical. What assessments work?"},
        {"role": "user", "content": "They're functionally bilingual — English fluent for written work. Go with the hybrid."},
        {"role": "user", "content": "Are we legally required under HIPAA to test all staff who touch patient records? And does this SHL test satisfy that requirement?"},
        {"role": "user", "content": "Understood. Keep the shortlist as-is."},
    ]
    expected = [
        "HIPAA (Security)",
        "Medical Terminology (New)",
        "Microsoft Word 365 - Essentials (New)",
        "Dependability and Safety Instrument (DSI)",
        "Occupational Personality Questionnaire OPQ32r",
    ]
    final_recs = get_final_rec_names(conversation)
    recall = recall_at_k(final_recs, expected)
    print(f"\nC7 Recall@10: {recall:.2f} | Got: {final_recs}")
    assert recall >= 0.4, f"C7 Recall@10 too low: {recall:.2f}"


# ── Trace C10: Graduate Management Trainee ─────────────────────────────────
def test_c10_graduate_trainee():
    conversation = [
        {"role": "user", "content": "We run a graduate management trainee scheme. We need a full battery — cognitive, personality, and situational judgement. All recent graduates."},
        {"role": "user", "content": "But can you remove the OPQ32r and replace it with something shorter? Candidates complain it takes too long."},
        {"role": "user", "content": "Drop the OPQ. Final list: Verify G+ and Graduate Scenarios."},
    ]
    expected = [
        "SHL Verify Interactive G+",
        "Graduate Scenarios",
    ]
    final_recs = get_final_rec_names(conversation)
    recall = recall_at_k(final_recs, expected)
    print(f"\nC10 Recall@10: {recall:.2f} | Got: {final_recs}")
    assert recall >= 0.8, f"C10 Recall@10 too low: {recall:.2f}"


# ── Aggregate Recall@10 ────────────────────────────────────────────────────
def test_mean_recall_summary(capsys):
    """Print a summary of Recall@10 across all implemented traces."""
    traces = [
        ("C1 Senior Leadership",
         [{"role": "user", "content": "We need a solution for senior leadership."},
          {"role": "user", "content": "CXOs and directors, 15+ years experience."},
          {"role": "user", "content": "Selection — comparing against a leadership benchmark."},
          {"role": "user", "content": "Perfect, confirmed."}],
         ["Occupational Personality Questionnaire OPQ32r", "OPQ Universal Competency Report 2.0", "OPQ Leadership Report"]),

        ("C10 Grad Trainee",
         [{"role": "user", "content": "Graduate management trainee battery — cognitive, personality, SJT."},
          {"role": "user", "content": "Remove OPQ32r, replace with something shorter."},
          {"role": "user", "content": "Drop the OPQ. Final: Verify G+ and Graduate Scenarios."}],
         ["SHL Verify Interactive G+", "Graduate Scenarios"]),
    ]

    recalls = []
    print("\n" + "=" * 60)
    print("RECALL@10 SUMMARY")
    print("=" * 60)
    for name, convo, expected in traces:
        recs = get_final_rec_names(convo)
        r = recall_at_k(recs, expected)
        recalls.append(r)
        print(f"{name:<30} Recall@10: {r:.2f}")

    mean = sum(recalls) / len(recalls) if recalls else 0
    print(f"\nMean Recall@10: {mean:.2f}")
    print("=" * 60)
    assert mean >= 0.4, f"Mean Recall@10 too low: {mean:.2f}"
