FROM python:3.12-slim
WORKDIR /app
COPY engine.py server.py consult.py handover.py synth.py mimic.py kmimic.py units.json concepts.json ./
COPY static ./static
COPY data ./data
ENV PORT=8000 PYTHONUNBUFFERED=1 LLM_BASE_URL=http://host.docker.internal:8091/v1
EXPOSE 8000
CMD ["python", "server.py"]
