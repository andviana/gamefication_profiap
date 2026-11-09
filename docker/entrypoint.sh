#!/bin/sh
# Prepara o ambiente a cada subida (passos idempotentes) e depois entrega o comando (gunicorn).
# O banco sobe VAZIO: o super admin raiz nasce na tela /setup (faça logo após a primeira subida).
set -e

echo "[entrypoint] aguardando o PostgreSQL..."
python docker/aguardar_servicos.py

echo "[entrypoint] aplicando migrações..."
flask db upgrade

echo "[entrypoint] pronto; iniciando: $*"
exec "$@"
