FROM postgis/postgis:14-3.2

# Добавляем clang в список зависимостей для сборки
RUN apt-get update && apt-get install -y \
    postgresql-server-dev-14 \
    gcc \
    make \
    git \
    clang \
    && rm -rf /var/lib/apt/lists/*

# Собираем pgvector 
RUN git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git \
    && cd pgvector \
    && make \
    && make install \
    && cd .. \
    && rm -rf pgvector

# Удаляем инструменты сборки, включая clang, чтобы образ остался чистым
RUN apt-get purge -y --auto-remove postgresql-server-dev-14 gcc make git clang