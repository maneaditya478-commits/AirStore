FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV AIRSTORE_MANAGER_HOST=0.0.0.0
ENV AIRSTORE_MANAGER_PORT=8000

EXPOSE 8000 8001 8002 8003

CMD ["python", "-m", "airstore.cli.main", "manager", "start"]
