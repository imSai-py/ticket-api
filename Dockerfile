# Multi-stage build for ticket-api

# Stage 1: Build React TypeScript Frontend
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Build Python dependencies
FROM python:3.11-slim AS python-builder

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Stage 3: Minimal runtime image
FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH \
    PORT=8000

# Copy installed dependencies from python-builder stage
COPY --from=python-builder /root/.local /root/.local

# Copy built frontend assets
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Copy application source and assets
COPY app/ ./app/
COPY data/ ./data/
COPY kb/ ./kb/
COPY web/ ./web/
COPY ticket_summary.py ./

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
