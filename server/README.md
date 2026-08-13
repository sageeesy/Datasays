# DataSays API

The backend is a FastAPI service for the bounded, evidence-first DataSays Agent. It owns CSV metadata, dataset profiling, metric retrieval, planning, Python generation, sandbox execution, validation, repair, conversation persistence, and analysis artifacts.

## Run

```bash
cp env.example .env
# Set OPENROUTER_API_KEY in .env
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The API is available at `http://127.0.0.1:8000`; OpenAPI documentation is at `/docs`.

## Main Endpoints

- `GET /health`
- `GET /api/files`
- `POST /api/files/upload`
- `GET /api/files/{file_id}`
- `DELETE /api/files/{file_id}`
- `POST /api/query`
- `GET|POST /api/conversations`
- `GET|PATCH|DELETE /api/conversations/{conversation_id}`
- `GET /api/conversations/{conversation_id}/runs`

`POST /api/query` accepts one or more uploaded file IDs and returns a compatibility envelope containing one verified Agent result. The direct-LLM comparison pipeline has been removed from the primary API; model and prompt comparison remains a secondary frontend evaluation surface that calls the same Agent path.

## Runtime Data

- `uploads/`: CSV files and JSON metadata
- `data/datasays.db`: conversations, messages, runs, and file associations

Both directories are ignored by Git. Use persistent volumes when running the service in containers.

## Sandbox

`USE_DOCKER=true` is the recommended mode. Build the image with:

```bash
docker build -t datasays-python-sandbox -f Dockerfile.python-sandbox .
```

`USE_DOCKER=false` runs generated Python directly and is only a development fallback. It is unsafe for a public service.

## Tests

```bash
python -m unittest discover -s tests -v
```

The LLM-backed benchmark is documented in `evals/README.md`.
