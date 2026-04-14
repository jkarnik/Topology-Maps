FROM python:3.12-slim

WORKDIR /app

# Install simulator + shared dependencies
COPY simulator/ simulator/
COPY server/models.py server/models.py
COPY server/__init__.py server/__init__.py

RUN pip install --no-cache-dir -r simulator/requirements.txt

# Expose SNMP agent UDP ports and REST API
EXPOSE 10161-10167/udp
EXPOSE 8001

CMD ["python", "-m", "simulator.main"]
