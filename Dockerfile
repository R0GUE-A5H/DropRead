FROM ghcr.io/r0gue-a5h/dropread-base:latest

COPY src/ ./src/
COPY frontend/ ./frontend/
COPY alembic/ ./alembic/
COPY alembic.ini ./

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "src.ai_newsletter.app:app", "--host", "0.0.0.0", "--port", "8000"]