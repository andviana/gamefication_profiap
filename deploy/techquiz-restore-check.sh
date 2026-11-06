#!/bin/sh
# Teste de restauração: restaura um backup num banco TEMPORÁRIO, conta as linhas das tabelas principais e apaga o banco.
# NÃO toca no banco de produção. Uso:  techquiz-restore-check.sh /var/backups/techquiz/techquiz-AAAAMMDD-HHMMSS.dump
# Exige um usuário do Postgres com permissão de criar banco (ex.: sudo -u postgres, ou PGUSER/PGHOST/PGPASSWORD no ambiente).
set -eu
arq="${1:?informe o arquivo .dump}"
[ -r "$arq" ] || { echo "arquivo não encontrado: $arq" >&2; exit 2; }
if [ -r "$arq.sha256" ]; then ( cd "$(dirname "$arq")" && sha256sum -c "$(basename "$arq").sha256" ); fi

tmp="techquiz_restore_$(date +%s)"
createdb "$tmp"
trap 'dropdb --if-exists "$tmp" >/dev/null 2>&1 || true' EXIT INT TERM
pg_restore --no-owner --no-privileges --exit-on-error --dbname="$tmp" "$arq"
echo "restauração concluída em $tmp. Linhas por tabela:"
for t in usuario campus curso grupo questionario pergunta alternativa coleta partida resposta; do
    n="$(psql -At -d "$tmp" -c "SELECT count(*) FROM $t")"
    printf '  %-14s %s\n' "$t" "$n"
done
psql -At -d "$tmp" -c "SELECT 'versão do schema: ' || version_num FROM alembic_version"
echo "OK: o backup restaura. Banco temporário removido."
