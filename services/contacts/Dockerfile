FROM python:3.12-slim
WORKDIR /app
COPY services/contacts/requirements.txt ./requirements.txt
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt || true; fi
RUN pip install --no-cache-dir "uvicorn[standard]" || true
COPY services/contacts/app ./app
COPY packages ./packages
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
