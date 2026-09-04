# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# Build deps for psycopg/asyncpg wheels, plus tesseract-ocr — the real
# OCR engine binary pytesseract (see requirements.txt) invokes via
# subprocess; it is NOT a Python package and is not installed by pip.
# OCR Processing Foundation — approved technology-selection experiment.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq-dev gcc curl tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# ---- Dependencies (cached layer) ----
FROM base AS deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ---- Runtime ----
FROM base AS runner
RUN groupadd --system app && useradd --system --gid app --uid 1001 app
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY . .
RUN chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health/live || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
