FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY config.example.yaml ./config.example.yaml

# Create default config from example if not mounted
RUN cp config.example.yaml config.yaml

EXPOSE 8895

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8895/health', timeout=5)"

CMD ["python", "-m", "src.proxy_server", "--config", "config.yaml"]
