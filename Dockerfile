FROM node:22-slim AS frontend
WORKDIR /build/web
COPY web/package*.json ./
RUN npm ci
COPY web ./
RUN npm run build

FROM debian:trixie-slim AS sevenzip
ADD https://github.com/ip7z/7zip/releases/download/26.05/7z2605-linux-x64.tar.xz /tmp/7zip.tar.xz
RUN apt-get update && apt-get install -y --no-install-recommends xz-utils \
    && mkdir /opt/7zip && tar -xJf /tmp/7zip.tar.xz -C /opt/7zip

FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/KazeLiu/telegram-file-downloader"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY LICENSE THIRD_PARTY_NOTICES.md ./
COPY src ./src
COPY --from=frontend /build/src/telegram_file_downloader/static ./src/telegram_file_downloader/static
COPY --from=sevenzip /opt/7zip /opt/7zip
RUN pip install --no-cache-dir . \
    && ln -s /opt/7zip/7zz /usr/local/bin/7zz \
    && useradd --create-home --uid 10001 app \
    && mkdir /data /downloads && chown app:app /data /downloads
USER app
CMD ["telegram-file-downloader-service"]
