FROM python:3.14-slim-bookworm
WORKDIR /app
RUN pip install --no-cache-dir "fastmcp>=4.0"
COPY server.py .
EXPOSE 9000
CMD ["python", "server.py"]
