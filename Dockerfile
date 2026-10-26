FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . && mkdir -p /data
ENV SPOOL_DIR=/data FLUSH_SECONDS=300 BOOK_SAMPLE_SECONDS=10
CMD ["orderflow", "collect"]
