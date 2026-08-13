# FastAPI Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY main.py .

# Create uploads directory with proper permissions
RUN mkdir -p /app/uploads/.metadata /app/data /tmp/datasays-sandbox && \
    chmod -R 755 /app/uploads /app/data /tmp/datasays-sandbox

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Health check (PORT is set by Railway, default to 8000)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application (use PORT from environment variable)
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}

