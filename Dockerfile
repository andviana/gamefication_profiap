# Imagem do TechQuiz para a VPS: gunicorn + Flask. O PostgreSQL sobe em outro contêiner (docker-compose.prod.yml).
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FLASK_APP=app:create_app

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

# O que vai para a imagem é decidido pelo .dockerignore (sem .env, testes, banco local nem .venv)
COPY . .

RUN chmod +x docker/entrypoint.sh \
 && useradd --system --uid 10001 --no-create-home app \
 && chown -R app:app /app

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD ["python", "docker/saude.py"]

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "-c", "deploy/gunicorn.conf.py", "wsgi:app"]
