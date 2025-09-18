FROM python:3.12-slim
WORKDIR /app
COPY services/webhook-dispatcher/requirements.txt ./requirements.txt
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt || true; fi
COPY services/webhook-dispatcher/worker.py ./worker.py
COPY packages ./packages
CMD ["python", "worker.py"]

