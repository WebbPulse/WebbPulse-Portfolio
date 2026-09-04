# WebbPulse

A full-stack personal portfolio and blog. Every section — projects, experience, skills, blog, and site copy — is driven from the API through an admin panel rather than hardcoded.

**Stack:** FastAPI (Python 3.13) on AWS Lambda · React (TypeScript) · DynamoDB · AWS (Terraform)

**License:** MIT

---

## Structure

```
backend/    FastAPI app, DynamoDB repositories, Lambda handler
frontend/   React + Vite + Tailwind CSS
terraform/  AWS infrastructure
docs/        Static assets (resume, etc.)
```

---

## Development

**Prerequisites:** Python 3.13, Node 18+, Docker (for DynamoDB Local)

### Backend

```bash
cd backend
docker compose up -d              # start DynamoDB Local on :8001
export DYNAMODB_ENDPOINT_URL=http://localhost:8001
python scripts/create_local_tables.py
uvicorn app.main:app --reload     # http://localhost:8000 (docs at /docs)
```

```bash
# Tests (moto-backed, no database needed)
pytest tests/

# Linting
flake8 app/ tests/ --max-line-length=88 --extend-ignore=E203,W503
black --check app/ tests/ && isort --check-only app/ tests/
```

See `backend/README.md` for configuration, the data model, and the Lambda build.

### Frontend

```bash
cd frontend
npm install
npm run dev:local     # port 5173, proxies /api to localhost:8000
npm run build
npm run lint
npm run test:run
```
