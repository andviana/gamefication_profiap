#!/bin/sh
# Backup do banco do TechQuiz na VPS (pg_dump compactado) com conferência, retenção por idade e cópia externa opcional.
# Rode na pasta do projeto (onde está o docker-compose.prod.yml):   sh docker/backup.sh
# Agendado toda semana pelo cron (guia, seção 12). Rode também À MÃO antes de trocar um gabarito, ao fim de cada coleta
# e antes de atualizar o sistema.
set -eu

PROJETO="${COMPOSE_PROJECT_NAME:-techquiz}"
ARQUIVO="${COMPOSE_ARQUIVO:-docker-compose.prod.yml}"
DIR="${BACKUP_DIR:-./backups}"
RETENCAO_DIAS="${BACKUP_RETENCAO_DIAS:-56}"          # 8 semanas
dc() { docker compose -p "$PROJETO" -f "$ARQUIVO" "$@"; }

umask 077
mkdir -p "$DIR"
destino="$DIR/techquiz-$(date +%Y%m%d-%H%M%S).dump"
parcial="$destino.parcial"
trap 'rm -f "$parcial"' EXIT INT TERM

# formato custom (-Fc): já vem compactado e permite restaurar tabelas isoladas
dc exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges' > "$parcial"
# confere que o arquivo é legível antes de aceitá-lo
dc exec -T db pg_restore --list < "$parcial" > /dev/null
mv "$parcial" "$destino"
( cd "$DIR" && sha256sum "$(basename "$destino")" > "$(basename "$destino").sha256" )
trap - EXIT INT TERM
echo "backup ok: $destino ($(du -h "$destino" | cut -f1))"

# cópia para fora da VPS (definida por você); se falhar, o script falha e nada é apagado
if [ -n "${BACKUP_COPIA_CMD:-}" ]; then
    sh -c "$BACKUP_COPIA_CMD" sh "$destino"
    echo "cópia externa ok"
fi

# retenção: só apaga os antigos DEPOIS de o novo estar pronto
find "$DIR" -maxdepth 1 -type f \( -name 'techquiz-*.dump' -o -name 'techquiz-*.dump.sha256' \) -mtime +"$RETENCAO_DIAS" -print -delete \
    | sed 's/^/removido (retenção): /'
