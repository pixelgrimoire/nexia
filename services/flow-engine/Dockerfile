FROM python:3.12-slim
WORKDIR /app
COPY services/flow-engine/requirements.txt ./requirements.txt
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt || true; fi
RUN pip install --no-cache-dir "uvicorn[standard]" || true
COPY services/flow-engine/worker ./worker
COPY packages ./packages
CMD ["python", "worker/engine_worker.py"]
