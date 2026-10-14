ARG PYTHON_IMAGE=python:3.11-slim
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN python -m pip install --no-cache-dir -r backend/requirements.txt \
    && useradd --create-home --uid 10001 appuser
COPY backend backend
USER appuser
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:create_application", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
