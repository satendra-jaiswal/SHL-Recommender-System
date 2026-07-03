# SHL Conversational Assessment Recommender — Architecture Plan (Beginner-Friendly Edition)

> This document explains **what** we're building, **why** each piece exists, and **how** it all
> fits together — written so that every decision can be explained in your own words in an
> interview. Wherever there's a technical term, it's explained the first time it's used.

---

## 1. What are we building, in one sentence?

A small web service that acts like a helpful recruiter's assistant: you chat with it about a
hiring need ("I need a Java developer"), and it asks a few smart questions, then gives you a
list of real SHL tests (with real links) that fit — and lets you tweak that list ("drop this",
"add that") without starting over.

```
 You (or the grader's simulated recruiter)
        │
        │  "I'm hiring a Java developer, mid-level, works with stakeholders"
        ▼
 ┌───────────────────────────────┐
 │   Our chat agent (this repo)   │
 └───────────────────────────────┘
        │
        │  "Got it. Here are 5 tests that fit:  [Java 8, OPQ32r, ...]"
        ▼
   You keep chatting: "actually make it entry-level" → list updates, doesn't restart
```

The two rules that make this a *real engineering problem* and not just "call an AI":

1. **We may only ever recommend real things from SHL's actual catalog** — never a name or link
   the AI made up.
2. **Our server has no memory.** Every single message we get contains the *entire* conversation
   so far, and we must reply consistently as if we remembered everything — even though, from our
   server's point of view, every request is a total stranger.

Everything below exists to solve those two rules well.

---

## 2. The tricky part: "no memory" (stateless design)

**Plain English analogy:** Imagine a phone support line where every time you call back, you get
a *different* agent who has never spoken to you before — but they're handed a full written
transcript of every call you've ever made, and have to pick up exactly where the last agent left
off, including remembering "we already agreed on these 3 items, don't relitigate them."

That's literally what our server does. There is no database, no session, no memory between
requests. The **entire** conversation (every message from both sides) is resent on every single
call. Our job is to *re-read the whole transcript every time* and behave consistently.

The dangerous failure mode: if our AI tries to "re-imagine" the shortlist from scratch on every
turn, small random variation in how the AI thinks can cause items to silently appear/disappear
between turns even though the user asked nothing about them. We saw proof this happens in one of
the sample conversations (`C9.md`) — the user asks two follow-up *questions* about an existing
list ("is Java Advanced the right pick?", "do we really need this test?") without asking for any
change, and the correct behavior is: **the list must stay 100% identical**, five turns in a row.

**Our fix ("pinning the list"):** we always print the shortlist in the exact same table format.
That means *we* can read our own *previous* reply back out of the conversation history and
recover "here's exactly what we already told the user" as a clean list — no guessing, no AI
needed for this step, just simple text parsing. Then we only ever *change* that list when the
user clearly asks for a change (add/drop/replace), applying that change with plain code (Python
list operations), never by asking an AI to "regenerate the whole list from memory."

```
 Turn 3 (our reply):                         Turn 5 (new request comes in):
 ┌───────────────────────────────┐           ┌──────────────────────────────────┐
 │ reply: "Here's your shortlist" │           │ messages: [ ..., turn 3's reply, │
 │ table:                         │  ────▶    │            turn 4, turn 5 ]      │
 │  | Java 8      | ... |         │  (this    │                                  │
 │  | OPQ32r      | ... |         │   whole   │  We scan backwards, find our own │
 └───────────────────────────────┘   thing    │  turn-3 table, and parse it back │
                                     comes     │  into: ["Java 8", "OPQ32r"]      │
                                     back to   │  = the "pinned shortlist"        │
                                     us as     └──────────────────────────────────┘
                                     plain
                                     text)
```

---

## 3. The data we're working with

We were given `shl_product_catalog.json` — 377 real SHL tests. A few things we double-checked
ourselves (don't take these on faith from the assignment doc — we verified them by writing small
scripts against the actual file):

- **Every test belongs to 1 or more of exactly 8 categories**, e.g. "Knowledge & Skills",
  "Personality & Behavior", "Simulations". SHL's website shows these as single-letter codes on
  its product pages: `K`, `P`, `S`, etc. Full mapping:

  | Category (in our JSON file) | Letter code |
  |---|---|
  | Ability & Aptitude | A |
  | Biodata & Situational Judgment | B |
  | Competencies | C |
  | Development & 360 | D |
  | Assessment Exercises | E |
  | Knowledge & Skills | K |
  | Personality & Behavior | P |
  | Simulations | S |

  Some tests have **more than one** category (e.g. a test that's both "Knowledge & Skills" *and*
  "Simulations" becomes `"K,S"`). We generate this ourselves from the data, always in the same
  A→S order, so it's 100% consistent — we don't copy this from the sample conversation files,
  because we found at least one place where a sample file's letter code didn't actually match
  what the real catalog says for that test.

- **The duration field is messy** — sometimes `"30 minutes"`, sometimes `"Untimed"`, sometimes
  just `""` (blank), `"-"`, `"TBC"`, `"N/A"`, or `"Variable"`. Our code just tries to pull out a
  number if there is one, and otherwise keeps the original text as-is for display without
  crashing.

- **The file has one weird formatting quirk** (a stray line-break stuck inside one product's
  name), and we confirmed Python's built-in JSON reader can handle it fine with one small setting
  (`strict=False`) — no need for anything fancier.

---

## 4. How the agent should behave (learned from the 10 example conversations)

We read all 10 sample conversations we were given and found a consistent pattern:

| Situation | What a good reply looks like |
|---|---|
| **Vague first message** ("we need an assessment") | Ask ONE clarifying question. Don't recommend yet. |
| **Enough info gathered** | Give a shortlist (a table), but still leave the door open — don't declare the conversation over yet. |
| **User says "yes", "confirmed", "that's good"** | *Now* mark the conversation as finished, repeating the (maybe slightly updated) list. |
| **User says "drop X" / "add Y" / "replace A with B"** | Update just that part of the list. Everything else must stay exactly the same. |
| **User asks "what's the difference between X and Y?"** | Answer using only facts from our catalog data — no table this turn, just an explanation. The list reappears next turn if they confirm. |
| **User asks a legal question** ("are we legally required to...") | Politely decline — that's outside scope — then keep going with the existing list next turn (don't throw away progress). |
| **The catalog has no perfect match** (e.g. "Rust developer" — SHL has no Rust test) | Say so honestly, and suggest the closest real alternatives — never invent a fake match. |
| **User pastes a full job description** instead of a short sentence | Treat it the same as any other request — pull out the relevant details. |

One more subtle pattern worth naming: several examples show the agent **proactively suggesting a
personality test (OPQ32r) even when the user didn't ask for one**, while clearly saying "you can
skip this if you don't want it." We'll copy this style (helpful suggestion + easy opt-out), not
as a hard rule, but as an example we show the AI so it writes in a similar voice.

---

## 5. The architecture — what happens inside one `/chat` call

Here's the full journey of a single incoming request, step by step:

```
 POST /chat  { messages: [ ...entire conversation so far... ] }
        │
        ▼
 STEP 0 — Quick safety check (plain code, no AI, near-instant)
   Does the latest message contain obvious red flags?
   e.g. "ignore your instructions", "reveal your system prompt",
        "am I legally required to..."
   ──▶ If yes: skip straight to a polite refusal. Done. (Fast + can't be
       broken even if our AI provider is down.)
        │  (no red flag found, keep going)
        ▼
 STEP 1 — Recover the "pinned shortlist"
   Scan backwards through the conversation for OUR last reply that had
   a table, and parse it back into a plain list of tests.
   (Empty list if this is a new conversation.)
        │
        ▼
 STEP 2 — Ask an LLM: "What is the user asking, right now?"   [AI CALL #1]
   Input:  the whole conversation + the pinned shortlist (by name)
   Output (structured, e.g. JSON):
     - intent: clarify / recommend / refine / compare / refuse
     - requirements so far: role, seniority, must-have skills, languages...
     - if refining: what changed (add "AWS"? drop "OPQ32r"? etc.)
     - is the user just confirming ("yes, that's good")?
        │
        ▼
 STEP 3 — Search the catalog (only if we need NEW tests)
   - If the user named a specific product ("OPQ32r", "GSA") → exact/fuzzy
     text match, no ambiguity.
   - Otherwise → meaning-based search ("semantic search", explained below)
     over the 377 tests, using the requirements from Step 2.
   Output: a short numbered list of the best-matching real catalog items.
        │
        ▼
 STEP 4 — Apply the change to the pinned shortlist (plain Python, no AI)
   pinned_shortlist + (add these) − (drop these) = updated shortlist
        │
        ▼
 STEP 5 — Ask an LLM: "Write the reply"                       [AI CALL #2]
   Input: the numbered candidate list from Step 3, the updated shortlist
          from Step 4 (as item NUMBERS, not free text), conversation so far
   Output: { reply_text: "...", chosen_numbers: [1, 3, 4] }
   IMPORTANT: the AI never types out a name or a URL itself — it only picks
   NUMBERS from a list we already verified is 100% real. We then look up
   those numbers in our own catalog data to build the final answer. This
   means a made-up test name or URL is *structurally impossible*, not just
   "unlikely."
        │
        ▼
 STEP 6 — Build the final JSON exactly in the required shape and return it
```

### Why two separate AI calls instead of one big one?

Think of it like a two-person team: one person's only job is "figure out what the customer
actually wants" (Step 2), and the second person's only job is "write a good reply using only the
approved options in front of them" (Step 5). Splitting it this way means:

- Each call has a smaller, simpler job → more reliable, less likely to go off the rails.
- We can search the catalog *in between* the two calls, using what call #1 figured out.
- If someone tries a prompt-injection trick, it would have to fool *two* separate, narrowly-
  scoped steps instead of one, which is harder.

### Retrieval: how we search 377 tests — hybrid approach (confirmed with you)

We compared two ways to search text:

- **Keyword matching** (a method called *TF-IDF*): counts matching words, gives more weight to
  rare/specific words. Great for exact terms like "Java", "SQL", or an exact product name like
  "OPQ32r" — bad at understanding paraphrases.
- **Meaning-based search** (called *embeddings*/*semantic search*): a small AI model converts
  text into a list of numbers representing its meaning, so "people who never cut corners, safety
  first" can correctly match a test called "Dependability and Safety Instrument" even though not
  one word is shared between them. This is genuinely important here — several of our 10 sample
  conversations describe needs in plain language rather than exact catalog wording.

**Decision:** we use **both**, each where it's strongest:
1. If the user names a specific product ("OPQ32r", "GSA", "SVAR") → look it up by exact/fuzzy
   text match. Reliable, no ambiguity, no AI model needed for this part.
2. Otherwise → meaning-based search over the whole catalog, so natural, paraphrased descriptions
   still find the right tests.

This costs almost nothing extra (the exact-match check is a tiny, fast library, not a second AI
model) and removes the main weakness of pure meaning-based search (mixing up similarly-worded
specific products).

---

## 6. Worked example — tracing C9 turn 5 through the pipeline

To make this concrete, here's exactly what happens on trace **C9**, turn 5, where the user asks
a question about an *existing* item and nothing should change:

> Prior shortlist (already shown to the user in turn 3-4): Java Advanced, Spring, SQL, AWS,
> Docker, Verify G+, OPQ32r.
> Turn 5 user message: *"On Java — they'd be working on existing services, not greenfield. Is
> the Advanced level the right pick?"*

1. **Step 0**: no red flags. Continue.
2. **Step 1**: we parse our own turn-4 reply's table → pinned shortlist = those exact 7 items.
3. **Step 2 (AI call)**: classifies this as `intent: refine`, `shortlist_delta.action: none`
   (they're asking a question, not requesting any change), `is_confirmation: false`.
4. **Step 3**: skipped entirely — no new items requested, so no search needed.
5. **Step 4**: pinned shortlist stays exactly the same (no add/drop to apply).
6. **Step 5 (AI call)**: writes a reply explaining *why* Advanced is the right level, referencing
   the existing candidates only for context — `chosen_numbers` = the same 7 items unchanged.
7. **Result**: identical table to turn 4, `end_of_conversation: false` (they haven't confirmed
   yet). ✅ Matches the expected behavior exactly, and there's no way for the list to drift,
   because we never asked an AI to "regenerate" it — we only ever added/removed on explicit
   request.

---

## 7. Guardrails — staying in scope and safe

Two layers, cheapest/fastest first:

1. **Layer 0 (no AI, instant):** a simple list of red-flag phrases we check the raw text against
   — things like "ignore previous instructions", "you are now a...", "reveal your prompt", or
   obvious legal phrasing ("legally required", "am I liable"). If hit, we refuse immediately
   without even calling an AI model — this makes refusal reliable even if our AI provider is
   slow or temporarily down.
2. **Layer 1 (part of AI call #1):** the same call that figures out what the user wants also
   double-checks "is this actually in scope?" — catching subtler cases Layer 0's simple phrase
   list would miss, like "what interview questions should I ask this candidate?" (general hiring
   advice, not about our catalog, but no obvious red-flag words).

A refusal never erases the pinned shortlist — it just skips answering that one question, and the
existing list comes back on the next turn if the user moves on (this matches the sample
conversation where a legal question is declined mid-conversation, then the prior shortlist
resumes).

---

## 8. Deciding "are we done?" (`end_of_conversation`)

Plain rule: **`true` only when there's already a shortlist AND the user's latest message is a
clear "yes, that works" / "confirmed" / "locking it in" type of message** — not just because we
showed a list. Showing a list is not the finish line; the user accepting it is.

Extra safety net: the assignment caps every conversation at **8 total messages** (both sides
combined). We count messages on every call, and:
- If we're about to hit that cap and still don't have a shortlist yet, we commit to a best-effort
  one anyway (using sensible default assumptions) rather than ending on an empty list — an empty
  list scores zero, a reasonable guess scores something.
- We never ask more than 2 clarifying questions in a row before committing to a shortlist, so we
  don't run out of turns just gathering information.

---

## 9. Two AI providers, automatic switch (as you requested)

We're required to support both **Groq** and **Gemini** (both have generous free tiers) and
switch automatically — not by hand-editing config — whenever one is slow, erroring, or rate-
limited. Design: a single plain function, `call_llm(...)`, tries Groq first (it's fast and has
a generous free quota), and if that fails or times out, automatically retries the exact same
request on Gemini. Both attempts have a short timeout (about 8-10 seconds each) so even in the
worst case (both attempted) we're comfortably inside the 30-second limit the assignment sets per
request.

We deliberately did **not** build a fancy plug-in system with abstract base classes for this —
just two small functions with the same shape, and one function that tries them in order. Simpler
to read, simpler to explain, and just as easy to swap providers.

---

## 10. Folder structure (what each file is responsible for, in plain words)

```
app/
  main.py            The actual web server — defines /health and /chat.
  config.py           All the settings (API keys, model names, timeouts) in one place.
  schemas.py          The exact shape of requests/replies the assignment requires.
  orchestrator.py      The "conductor" — runs steps 0-6 above in order for every /chat call.

  catalog/
    loader.py          Reads shl_product_catalog.json, cleans it up, figures out each test's
                       letter code (A/B/C/.../S), and turns messy duration text into numbers
                       where possible.
    models.py          The Python shape of "one SHL test" (name, url, category, duration...).
    data/               Where we save the pre-computed catalog + its search vectors, so the
                       server doesn't have to redo that work every time it starts up.

  retrieval/
    embedder.py         Turns a piece of text into the "meaning vector" used for search.
    search.py            Given what the user wants, returns the best-matching real tests.
    name_resolver.py     Matches a name the user typed ("OPQ") to the real catalog entry, even
                       if they didn't type it exactly right.

  llm/
    groq_client.py       Talks to Groq.
    gemini_client.py      Talks to Gemini.
    router.py             Tries Groq, falls back to Gemini automatically if needed.

  agent/
    table_format.py       Turns a shortlist into the table we show the user, and can also read
                       that same table back out of old messages (this is the "memory trick").
    guardrails.py          The Layer-0 quick red-flag check (no AI).
    state_extractor.py     AI call #1 — "what does the user want, right now?"
    policy.py               Plain code that decides: clarify, recommend, refine, compare, or
                       refuse — and whether we're actually done.
    responder.py            AI call #2 — "write the reply, using only approved options."

scripts/
  build_embeddings.py      Run once, ahead of time: computes the "meaning vectors" for all 377
                       tests so the live server doesn't have to.

eval/
  simulated_user.py         A little AI "pretend recruiter" we can use to test our own agent by
                       actually chatting with it, the same way the real grader will.
  traces/personas.json       The persona + facts + expected answer for each of the 10 examples.
  replay_harness.py           Runs simulated conversations and scores how many of the "correct"
                       tests we actually recommended.
  probes.py                    Quick pass/fail checks (e.g. "does it refuse off-topic questions?",
                       "does every link we return actually exist in the catalog?").

tests/                        Small automated checks for the trickier pieces (parsing, table
                       round-tripping, edge cases in the decision logic).
Dockerfile                    Recipe for packaging the app to deploy on Hugging Face Spaces.
requirements.txt / .env.example / README.md
APPROACH.md                   The 2-page write-up required for submission.
```

---

## 11. Biggest risks and how we handle them

| Risk | How we prevent it |
|---|---|
| Shortlist randomly changes between turns even when nothing was asked | We "pin" it by reading our own last table back out, and only ever change it with plain add/remove code — never by asking AI to regenerate it from scratch. |
| AI makes up a test name or a fake URL | Structurally impossible: the AI can only pick *numbers* from a pre-verified list; we build the final names/URLs ourselves by looking those numbers up in our own catalog. |
| Request takes too long (30s limit) | Only 2 AI calls per request, each with an 8-10 second timeout; the catalog search is instant (no AI involved); the safety check in Step 0 needs no AI call at all. |
| Conversation runs out of its 8-message limit | We count messages every turn and force a real (if imperfect) shortlist before we run out, instead of ending empty-handed. |
| Both AI providers are down at once | We return a safe, honest "having trouble, please try again" reply instead of crashing. |
| Our local testing doesn't reflect how the real grader behaves | The real grader uses an AI that pretends to be a recruiter and answers *our* questions live — it's not replaying the fixed example scripts. So instead of just replaying the 10 examples word-for-word (which wouldn't work, since our agent may ask different questions than the example did), we build our own small "pretend recruiter" AI to test against, the same way the real grader will. |

---

## 12. Build order — small, testable steps

We build this in an order where each step can be checked before moving to the next, instead of
writing everything at once and debugging a huge pile of code:

1. **Catalog loader** — load the 377 tests, clean them up, check we still have exactly 377 and
   nothing crashed.
2. **Table format** — write a shortlist to text, then read it back, and check we get the exact
   same list out.
3. **Search** — precompute the meaning vectors, then sanity-check a few hand-picked searches
   ("Java developer", "safety plant operator") return sensible results.
4. **Basic web server** — get `/health` and `/chat` up and running (with fake canned replies at
   first), so we have something real to test against early.
5. **AI provider connections** — connect Groq and Gemini, and prove the automatic fallback
   actually works by temporarily breaking one on purpose.
6. **Understand the user** — build the guardrails + AI call #1, test on a handful of realistic
   messages (vague request, pasted job description, an injection attempt, a legal question).
7. **Decide + respond** — build the decision logic and AI call #2, and wire the whole pipeline
   together end-to-end.
8. **Quick behavior checks** — automated pass/fail tests (refuses off-topic? doesn't recommend
   on a vague first message? honors a "drop X" request? never returns a fake URL?).
9. **Full simulated conversations** — build the "pretend recruiter" tester and run whole
   conversations against our own agent, scoring how many correct tests we found.
10. **Package + deploy** — build the Docker image, deploy to Hugging Face Spaces, confirm it
    wakes up within the allowed 2 minutes.
11. **Write the approach document** — using real numbers from step 9, not guesses.

---

## 13. How we'll know it actually works

- Automated checks (`pytest`) run before every deploy.
- The "pretend recruiter" test harness prints a score (0-100%) for how many correct tests we
  found across all 10 examples — we use this to compare ideas, not just as a one-time pass/fail.
- Before calling any step "done," we manually chat with the running server through a full
  conversation ourselves: ask something vague → get a clarifying question → get a shortlist →
  ask for a change → ask a comparison question → confirm → check the conversation is marked
  finished.
- After deploying, we test the *live, public* URL the same way (not just our own laptop),
  because that's what the real grader will actually connect to.
