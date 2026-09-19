FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 경로는 backend/app 기준 상대 경로(parents[2])로 잡혀 있어 레포 구조를 그대로 둔다.
COPY backend/ backend/
COPY data/address_code.csv data/
COPY vectorDB/ vectorDB/

# Cloud Run이 PORT를 주입한다. 로컬 docker run은 8080.
CMD exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8080}
