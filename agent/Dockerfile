FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV PYTHONPATH=/app
ENV DECIDER_MODE=mock
ENV CRM_BASE_URL=http://crm:8000
ENV LEDGER_BASE_URL=http://ledger:8081

CMD ["python", "agent/main.py"]
