FROM python:3.15.1-slim-bookworm
WORKDIR /app
RUN pip install --no-cache-dir "fastmcp>=4.1.2"
COPY server.py .
EXPOSE 9000
CMD ["python", "server.py"]
