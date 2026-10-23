FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/services/crm

ENV CRM_PORT=8000
ENV LEDGER_BASE_URL=http://ledger:8081
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "services.crm.main:app", "--host", "0.0.0.0", "--port", "8000"]
