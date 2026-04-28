FROM python:3.12-slim
WORKDIR /app
COPY nr_ingest/requirements.txt /app/nr_ingest/requirements.txt
RUN pip install --no-cache-dir -r /app/nr_ingest/requirements.txt
COPY nr_ingest/ /app/nr_ingest/
COPY server/ /app/server/
CMD ["python", "/app/nr_ingest/scheduler.py"]
