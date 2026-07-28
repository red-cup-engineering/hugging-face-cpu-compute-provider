FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860

RUN groupadd --gid 10001 compute \
    && useradd --uid 10001 --gid compute --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin compute \
    && install -d -o compute -g compute -m 0555 /app

COPY --chown=compute:compute --chmod=0444 src/server.py /app/server.py

USER 10001:10001
EXPOSE 7860

CMD ["python", "/app/server.py"]
