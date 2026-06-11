FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd --create-home --shell /usr/sbin/nologin appuser && mkdir -p /app/data/uploads /app/data/logs && chown -R appuser:appuser /app
ENV PYTHONPATH=/app
ENV PORT=8000
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
