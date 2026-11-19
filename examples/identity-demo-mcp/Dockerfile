FROM python:3.15.2-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9
WORKDIR /app
RUN pip install --no-cache-dir "fastmcp>=4.1.2" "httpx>=0.28" "uvicorn>=0.38"
COPY server.py .
EXPOSE 9000
CMD ["python", "server.py"]
