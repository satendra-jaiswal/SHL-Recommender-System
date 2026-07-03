FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cache the embedding model at image build time so startup index builds do not
# spend their first request window downloading model files.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy application code
COPY . .

# HF Spaces uses port 7860
EXPOSE 7860

# Build data/chroma_db/ at startup if it was not included in the image,
# then start the FastAPI service.
CMD ["sh", "-c", "if [ ! -f data/chroma_db/chroma.sqlite3 ]; then echo 'Chroma index missing; building data/chroma_db ...'; python scripts/build_index.py; else echo 'Using existing Chroma index.'; fi; uvicorn app.main:app --host 0.0.0.0 --port 7860"]
