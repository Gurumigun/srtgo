FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY requirements-bot.txt .
RUN pip install --no-cache-dir -r requirements-bot.txt

# 소스 복사
COPY srtgo/ srtgo/
COPY bot/ bot/
COPY pyproject.toml .

# srtgo 패키지 설치 (SRT/KTX 클라이언트)
RUN pip install --no-cache-dir -e .

# 데이터 디렉토리
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "bot.main"]
