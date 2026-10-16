# Build context is the repo root (see docker-compose.yml) so api/ lands as a package under /app
# and `python -m api.…` / `pytest` work from /app.
FROM python:3.12-slim
WORKDIR /app
COPY api/requirements.txt api/requirements-dev.txt api/
RUN pip install --no-cache-dir -r api/requirements-dev.txt
COPY pyproject.toml weights.json ./
COPY api/ api/
COPY seed/ seed/
COPY tests/ tests/
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
