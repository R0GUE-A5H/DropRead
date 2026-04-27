FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Playwright + Xvfb
RUN apt-get update && apt-get install -y \
    tini \
    xvfb \
    wget gnupg ca-certificates \
    libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first
COPY pyproject.toml uv.lock ./

# Install uv
RUN pip install --no-cache-dir uv

# Install the project and all dependencies into the system Python
# Using `uv pip install .` reads pyproject.toml correctly and resolves all transitive deps.
RUN uv pip install --system .

# Install Playwright browsers (the playwright package is now installed)
RUN python -m playwright install chromium \
    && python -m playwright install-deps chromium

# Copy application code
COPY src/ ./src/
COPY frontend/ ./frontend/
COPY alembic/ ./alembic/
COPY alembic.ini ./

EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
# Start virtual display and FastAPI app
CMD ["sh", "-c", "Xvfb :99 -screen 0 1280x1024x24 & export DISPLAY=:99 && uvicorn src.ai_newsletter.app:app --host 0.0.0.0 --port 8080"]
