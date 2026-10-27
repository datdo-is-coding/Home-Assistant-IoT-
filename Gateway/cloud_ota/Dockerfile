FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY Gateway/cloud_ota/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY Gateway/gateway/__init__.py /app/gateway/__init__.py
COPY Gateway/gateway/fleet_ota /app/gateway/fleet_ota
USER 10001:10001
CMD ["python", "-m", "gateway.fleet_ota.service"]
