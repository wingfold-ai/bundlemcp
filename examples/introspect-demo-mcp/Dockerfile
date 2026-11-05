FROM python:3.15.1-slim-bookworm@sha256:575f8bc12ec26542e0678bc6b60e385218248019d433157ec327264a78c3a853
WORKDIR /app
# fastmcp 4 no longer brings httpx, which the introspection call needs.
RUN pip install --no-cache-dir "fastmcp>=4.1.2" "httpx>=0.28"
COPY server.py .
EXPOSE 9000
CMD ["python", "server.py"]
