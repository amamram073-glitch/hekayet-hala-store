FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/workspace/apps/api:/workspace
WORKDIR /workspace
COPY apps/api/requirements.txt /workspace/apps/api/requirements.txt
RUN pip install --no-cache-dir -r /workspace/apps/api/requirements.txt && useradd --create-home --uid 10001 appuser
COPY apps/api /workspace/apps/api
COPY services/worker /workspace/services/worker
RUN mkdir -p /var/lib/cybershield/reports /var/lib/cybershield/evidence && chown -R appuser:appuser /var/lib/cybershield
WORKDIR /workspace/apps/api
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
