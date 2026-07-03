# SHL Assessment Recommender

A conversational FastAPI service that recommends SHL assessments based on job descriptions and hiring needs.

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set your Gemini API key

```powershell
# Windows PowerShell
$env:GOOGLE_API_KEY = "your-gemini-api-key"
```

```bash
# Mac/Linux
export GOOGLE_API_KEY="your-gemini-api-key"
```

Or copy `.env.example` to `.env` and fill in your key.

### 3. Build the catalog (scrape + index)

```bash
# Step 3a: Scrape the SHL catalog → data/catalog.json
python scripts/catalog_scraper.py

# Step 3b: Build vector index → data/chroma_db/
python scripts/build_index.py
```

### 4. Run the server

```bash
uvicorn app.main:app --reload --port 8000
```

### 5. Test

```bash
# Health check
curl http://localhost:8000/health

# Chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "I need assessments for a Java developer"}]}'
```

---

## API Reference

### GET /health

Returns `{"status": "ok"}` when the service is running.

### POST /chat

**Request:**
```json
{
  "messages": [
    {"role": "user", "content": "string"},
    {"role": "assistant", "content": "string"}
  ]
}
```

**Response:**
```json
{
  "reply": "string",
  "recommendations": [
    {
      "name": "string",
      "url": "string",
      "test_type": "string"
    }
  ],
  "end_of_conversation": false
}
```

---

## Running Tests

```bash
# Schema compliance + URL validation
pytest tests/test_schema.py -v

# Trace replay + Recall@10
pytest tests/test_traces.py -v -s

# Behavior probes
pytest tests/test_probes.py -v

# All tests
pytest tests/ -v
```

---

## Project Structure

```
shl-recommender/
├── app/
│   ├── main.py        FastAPI app: /health and /chat
│   ├── agent.py       Core pipeline: retrieve → prompt → LLM → validate
│   ├── retriever.py   ChromaDB loader + retrieve() + is_valid_url()
│   ├── prompt.py      System prompt builder with 10 rules
│   └── schemas.py     Pydantic request/response models
├── data/
│   ├── catalog.json   SHL product catalog
│   └── chroma_db/     Pre-built vector index (commit this!)
├── scripts/
│   ├── catalog_scraper.py  Scrape SHL catalog → catalog.json
│   └── build_index.py      Embed catalog → ChromaDB
├── tests/
│   ├── test_schema.py  Hard evals
│   ├── test_traces.py  Recall@10
│   └── test_probes.py  Behavior probes
├── Dockerfile
├── requirements.txt
└── ARCHITECTURE.md
```

---

## Deployment on Hugging Face Spaces

1. Create a new HF Space (Docker SDK)
2. Push this repo to the Space
3. Set `GOOGLE_API_KEY` as a Space Secret
4. The service starts automatically — `data/chroma_db/` is pre-built so startup is instant

---

## Tech Stack

| Layer | Tool |
|-------|------|
| LLM | Gemini 2.5 Flash |
| LLM Framework | LangChain |
| Embeddings | all-MiniLM-L6-v2 |
| Vector Store | ChromaDB |
| API | FastAPI |
