# /etc/nginx/techquiz-proxy.inc  (incluído pelo site)
proxy_pass http://techquiz_app;
proxy_http_version 1.1;
proxy_set_header Connection "";
proxy_set_header Host $http_host;
# SOBRESCREVE (não acrescenta) o X-Forwarded-For com o IP que o Nginx viu: um cliente não consegue forjar o IP
# para escapar do rate limit. Com PROXIES_CONFIAVEIS=1 o app usa este valor.
# Se houver OUTRO proxy/balanceador da instituição na frente do Nginx, use o módulo realip (set_real_ip_from)
# para que $remote_addr seja o IP do aluno, e confira o resultado na homologação (ver README_OPERACAO.md).
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $http_host;
proxy_read_timeout 60s;
proxy_send_timeout 60s;
