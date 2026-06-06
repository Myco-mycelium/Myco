# myco/Dockerfile
FROM python:3.12-slim

# Security: run as non-root user
RUN useradd -m -u 1000 myco && \
    apt-get update && apt-get install -y --no-install-recommends \
        build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .
RUN pip install --no-cache-dir -e . --no-deps

# Create data directory owned by myco user
RUN mkdir -p data && chown -R myco:myco /app

USER myco

EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["python3", "-m", "uvicorn", "api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--no-access-log", "--log-level", "info"]
