# Multi-stage build for ticket-api

# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Stage 2: Minimal runtime image
FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH \
    PORT=8000

# Copy installed dependencies from builder stage
COPY --from=builder /root/.local /root/.local

# Copy application source and assets
COPY app/ ./app/
COPY data/ ./data/
COPY kb/ ./kb/
COPY web/ ./web/

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
