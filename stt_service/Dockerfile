# Сборка: docker compose up -d --build stt-service
FROM mwader/static-ffmpeg:7.1 AS ffmpeg
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    HF_HOME=/models/huggingface

# RUN apt-get update \
#    && apt-get install -y --no-install-recommends ffmpeg \
#    && rm -rf /var/lib/apt/lists/*


COPY --from=ffmpeg /ffmpeg /usr/local/bin/ffmpeg

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd --create-home --uid 10001 stt \
    && mkdir -p /models \
    && chown -R stt:stt /models /app
USER stt

EXPOSE 8081

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]
