#!/bin/sh
# Backup do banco do TechQuiz (pg_dump compactado) com retenção por idade e cópia opcional para fora do servidor.
# Uso:  techquiz-backup.sh            (lê /etc/techquiz/techquiz.env)
# Rodado toda semana pelo techquiz-backup.timer. Rode também À MÃO antes de trocar um gabarito e ao fim de cada coleta.
# POSIX sh: não depende de bash.
set -eu

ENV_FILE="${TECHQUIZ_ENV:-/etc/techquiz/techquiz.env}"

# O arquivo de ambiente NÃO é executado (valores com espaço, como INSTITUICAO_NOME, quebrariam um "source" e o conteúdo
# seria tratado como comando). Só lemos, linha a linha, as chaves de que o backup precisa. Variáveis já definidas no
# ambiente (o systemd carrega o arquivo pelo EnvironmentFile) têm prioridade.
le_var() {
    nome="$1"
    eval "atual=\${$nome:-}"
    [ -n "$atual" ] && return 0
    [ -r "$ENV_FILE" ] || return 0
    valor="$(sed -n "s/^$nome=//p" "$ENV_FILE" | tail -n 1)"
    case "$valor" in \"*\") valor="${valor#\"}"; valor="${valor%\"}" ;; \'*\') valor="${valor#\'}"; valor="${valor%\'}" ;; esac
    [ -n "$valor" ] && export "$nome=$valor"
    return 0
}
for chave in DATABASE_URL BACKUP_DIR BACKUP_RETENCAO_DIAS BACKUP_COPIA_CMD; do le_var "$chave"; done

: "${DATABASE_URL:?DATABASE_URL não definida (confira $ENV_FILE)}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/techquiz}"
RETENCAO_DIAS="${BACKUP_RETENCAO_DIAS:-56}"          # 8 semanas

umask 077
mkdir -p "$BACKUP_DIR"
carimbo="$(date +%Y%m%d-%H%M%S)"
destino="$BACKUP_DIR/techquiz-$carimbo.dump"
parcial="$destino.parcial"

# libpq entende postgresql:// ; o "+psycopg" só existe dentro do app
url="$(printf '%s' "$DATABASE_URL" | sed 's|^postgresql+psycopg://|postgresql://|; s|^postgres://|postgresql://|')"

trap 'rm -f "$parcial"' EXIT INT TERM
# formato custom (-Fc): já vem compactado e permite restaurar tabelas isoladas
pg_dump --format=custom --no-owner --no-privileges --dbname="$url" --file="$parcial"
# confere que o arquivo é legível antes de aceitá-lo
pg_restore --list "$parcial" >/dev/null
mv "$parcial" "$destino"
( cd "$BACKUP_DIR" && sha256sum "$(basename "$destino")" > "$(basename "$destino").sha256" )
trap - EXIT INT TERM

echo "backup ok: $destino ($(du -h "$destino" | cut -f1))"

# cópia para fora do servidor (definida pela TI); falha aqui NÃO apaga nada e faz o serviço falhar, para alguém notar
if [ -n "${BACKUP_COPIA_CMD:-}" ]; then
    sh -c "$BACKUP_COPIA_CMD" sh "$destino"
    echo "cópia externa ok"
fi

# retenção: só apaga backups antigos DEPOIS de o novo estar pronto
find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'techquiz-*.dump' -o -name 'techquiz-*.dump.sha256' \) -mtime +"$RETENCAO_DIAS" -print -delete \
    | sed 's/^/removido (retenção): /'
