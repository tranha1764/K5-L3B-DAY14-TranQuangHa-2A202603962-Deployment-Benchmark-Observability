# Stage 1: builder — cài dependencies vào /install
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: runtime — base image slim, không chứa build/cache thừa
FROM python:3.11-slim AS runtime

WORKDIR /app

# Tạo user non-root
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy các thư viện Python đã cài từ stage builder
COPY --from=builder /install /usr/local

# Copy source code app và mock_llm
COPY app/ ./app/
COPY utils/ ./utils/

RUN chown -R appuser:appuser /app
USER appuser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health')" || exit 1

# Dùng exec để uvicorn là PID 1, nhận SIGTERM trực tiếp và đọc biến PORT từ platform
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
