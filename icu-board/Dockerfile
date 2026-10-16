FROM python:3.12-slim
WORKDIR /app
COPY engine.py server.py consult.py handover.py nurse_portal.py synth.py mimic.py kmimic.py units.json concepts.json planner_core.py planner_agent.py planner_evaluate.py pod_env.py pod_check.py ./
COPY static ./static
COPY data ./data
ENV PORT=8000 PYTHONUNBUFFERED=1 LLM_BASE_URL=http://host.docker.internal:8091/v1
EXPOSE 8000
CMD ["python", "server.py"]
