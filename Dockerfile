# Build:  docker build -t nextread .      Run:  docker run -p 8000:8000 nextread
FROM python:3.12-slim
LABEL org.opencontainers.image.title="nextread" \
      org.opencontainers.image.description="NextRead - a book recommendation product (FastAPI + vanilla JS)"
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
