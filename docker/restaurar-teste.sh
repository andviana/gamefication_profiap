#!/bin/sh
# Teste de restauração: restaura um backup num banco TEMPORÁRIO dentro do contêiner do PostgreSQL, conta as linhas das
# tabelas principais e apaga o temporário. NÃO toca no banco de produção.
# Uso (na pasta do projeto):   sh docker/restaurar-teste.sh backups/techquiz-AAAAMMDD-HHMMSS.dump
set -eu
arq="${1:?informe o arquivo .dump}"
[ -r "$arq" ] || { echo "arquivo não encontrado: $arq" >&2; exit 2; }
PROJETO="${COMPOSE_PROJECT_NAME:-techquiz}"
ARQUIVO="${COMPOSE_ARQUIVO:-docker-compose.prod.yml}"
dc() { docker compose -p "$PROJETO" -f "$ARQUIVO" "$@"; }

if [ -r "$arq.sha256" ]; then ( cd "$(dirname "$arq")" && sha256sum -c "$(basename "$arq").sha256" ); fi

tmp="techquiz_restore_$(date +%s)"
dc exec -T db sh -c "createdb -U \"\$POSTGRES_USER\" $tmp"
limpar() { dc exec -T db sh -c "dropdb -U \"\$POSTGRES_USER\" --if-exists $tmp" >/dev/null 2>&1 || true; }
trap limpar EXIT INT TERM
dc exec -T db sh -c "pg_restore -U \"\$POSTGRES_USER\" --no-owner --no-privileges --exit-on-error -d $tmp" < "$arq"
echo "restauração concluída no banco temporário. Linhas por tabela:"
for t in usuario campus curso grupo questionario pergunta alternativa coleta partida resposta; do
    n="$(dc exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -At -d $tmp -c 'SELECT count(*) FROM $t'")"
    printf '  %-14s %s\n' "$t" "$n"
done
dc exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -At -d $tmp -c \"SELECT 'versão do schema: ' || version_num FROM alembic_version\""
echo "OK: o backup restaura. Banco temporário removido."
