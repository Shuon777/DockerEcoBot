FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# По умолчанию PyTorch для CPU (~200 МБ вместо ~2.5 ГБ с CUDA).
# Для сервера с видеокартой: docker compose build --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu124 annotator
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir torch torchvision --index-url ${TORCH_INDEX}
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

EXPOSE 8010
# Один воркер uvicorn: модели и очередь задач живут в одном процессе
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
