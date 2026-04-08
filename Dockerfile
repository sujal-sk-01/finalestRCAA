FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scenarios ./scenarios
COPY server ./server
COPY baseline ./baseline
COPY static ./static
COPY models.py ./models.py
COPY inference.py ./inference.py
COPY openenv.yaml ./openenv.yaml
COPY .env.example ./.env.example
COPY README.md ./README.md

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/tasks', timeout=3)"

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
