FROM python:3.12-slim
WORKDIR /app
COPY backend /app/backend
COPY data /app/data
COPY models /app/models
RUN pip install --no-cache-dir /app/backend
ENV PYTHONPATH=/app/backend/src SPORTSWORLD_ENV=demo
EXPOSE 8000
CMD ["uvicorn","sportsworld.api.main:app","--host","0.0.0.0","--port","8000"]
