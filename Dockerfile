# Hugging Face Spaces (Docker SDK, free CPU: 2 vCPU / 16 GB RAM). Also runs anywhere Docker runs.
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/home/user/.cache/huggingface SHRAG_WORK=/tmp/shrag
RUN useradd -m -u 1000 user
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY --chown=user . /app
# (the scikit-learn version recorded in the bundle is installed at start-up if it differs: see ensure_versions in app.py)
USER user
EXPOSE 7860
CMD ["uvicorn", "app:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "7860"]
