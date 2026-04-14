FROM python:3.12-slim

WORKDIR /app

# Install server + collector + shared simulator constants
COPY server/ server/
COPY collector/ collector/
COPY simulator/__init__.py simulator/__init__.py
COPY simulator/constants.py simulator/constants.py

RUN pip install --no-cache-dir -r server/requirements.txt -r collector/requirements.txt

EXPOSE 8000

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
