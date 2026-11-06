#!/bin/sh
# Verificação pós-deploy (homologação e produção). Não grava nada.
# Uso:  smoke-test.sh https://techquiz.exemplo.ufra.edu.br [http://endereco-http, se a porta 80 não for a padrão]
set -u
base="${1:?informe a URL base, ex.: https://techquiz.exemplo.ufra.edu.br}"
base="${base%/}"
falhas=0
ok()   { printf '  OK     %s\n' "$1"; }
erro() { printf '  FALHA  %s\n' "$1"; falhas=$((falhas + 1)); }
cod()  { curl -sk -o /dev/null -w '%{http_code}' "$@"; }
cab()  { curl -sk -D - -o /dev/null "$@" | tr -d '\r'; }

echo "Verificando $base"
[ "$(cod "$base/saude")" = "200" ] && ok "/saude responde 200 (banco e schema em dia)" || erro "/saude não respondeu 200"

http="${2:-http://${base#https://}}"
r="$(cod --max-redirs 0 "$http/")"
[ "$r" = "301" ] && ok "HTTP redireciona para HTTPS" || erro "HTTP não redireciona (código $r)"

h="$(cab "$base/entrar")"
echo "$h" | grep -qi '^strict-transport-security:' && ok "HSTS presente" || erro "sem Strict-Transport-Security"
echo "$h" | grep -qi '^content-security-policy:.*script-src .self.' && ok "CSP presente" || erro "sem Content-Security-Policy"
echo "$h" | grep -qi '^x-frame-options: deny' && ok "X-Frame-Options: DENY" || erro "sem X-Frame-Options: DENY"
echo "$h" | grep -qi '^cache-control: no-store' && ok "páginas do painel sem cache" || erro "painel sem Cache-Control: no-store"
echo "$h" | grep -qi '^server: .*[0-9]\.[0-9]' && erro "o Nginx expõe a versão (server_tokens off)" || ok "versão do servidor não exposta"

[ "$(cod "$base/")" = "200" ] && ok "jogo servido na raiz" || erro "jogo não abriu em /"
[ "$(cod "$base/static/game/js/api.js")" = "200" ] && ok "arquivos estáticos servidos" || erro "estáticos fora do ar"
[ "$(cod "$base/admin/")" = "302" ] && ok "painel exige login" || erro "/admin/ não redireciona para o login"
[ "$(cod "$base/admin/api/dashboard/questionarios")" = "401" ] && ok "API do dashboard exige login (401)" || erro "API do dashboard aberta"

r="$(curl -sk -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{"codigo":"ZZZZZ"}' "$base/api/coleta/iniciar")"
[ "$r" = "404" ] || [ "$r" = "429" ] && ok "API do jogo recusa código inexistente ($r)" || erro "API do jogo respondeu $r para um código inexistente"

# o IP que o app enxerga precisa ser o do cliente (rate limit): confira à mão em README_OPERACAO.md, seção "IP real"
echo
if [ "$falhas" -eq 0 ]; then echo "Tudo certo."; else echo "$falhas verificação(ões) falharam."; exit 1; fi
