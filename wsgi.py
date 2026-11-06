"""Ponto de entrada de produção (gunicorn wsgi:app). Falha ao subir se o schema do banco estiver desatualizado."""
from app import create_app

app = create_app(verificar_schema=True)
