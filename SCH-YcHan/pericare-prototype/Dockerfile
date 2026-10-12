FROM python:3.12-slim
WORKDIR /app
RUN groupadd --gid 10001 pericare && useradd --uid 10001 --gid pericare --create-home pericare
COPY --chown=pericare:pericare app ./app
COPY --chown=pericare:pericare static ./static
COPY --chown=pericare:pericare examples ./examples
COPY --chown=pericare:pericare docs ./docs
COPY --chown=pericare:pericare scripts ./scripts
COPY --chown=pericare:pericare server.py ./server.py
RUN mkdir -p /app/data && chown pericare:pericare /app/data
USER pericare
ENV PORT=8000 HOST=0.0.0.0 DATA_DIR=/app/data PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 MODEL_BACKEND=demo
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=4s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3)"
CMD ["python", "server.py"]
