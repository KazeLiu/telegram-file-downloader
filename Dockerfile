FROM python:3.12-slim

LABEL org.opencontainers.image.version="1.1.0" \
    org.opencontainers.image.source="https://github.com/iljacc/telegram-file-downloader"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 app

USER app
CMD ["telegram-file-downloader-service"]
