"""Configuração do gunicorn (modelo). Lida pelo systemd: gunicorn -c /opt/techquiz/app/deploy/gunicorn.conf.py wsgi:app"""
import os

# Só ouve em localhost: quem atende a internet é o Nginx (HTTPS).
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")

# Processos: o rate limit e as sessões não dependem de memória do processo (ficam no banco e no cookie),
# então qualquer número de workers é seguro. Regra prática: de 2 a 4 por núcleo, a ajustar na homologação.
workers = int(os.environ.get("WEB_CONCURRENCY", "3"))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "4"))

timeout = 30              # o dashboard mais pesado leva menos de 1 s; 30 s só protege contra processo travado
graceful_timeout = 20
keepalive = 5
max_requests = 2000       # recicla o processo de vez em quando (contra vazamento de memória)
max_requests_jitter = 200

# Sem o socket de controle do gunicorn (ele tenta gravar no diretório do usuário, que o serviço e o contêiner não têm).
control_socket_disable = True

# Logs vão para o journald (stdout/stderr). O log de acesso não inclui o corpo (códigos e respostas) das requisições.
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")
access_log_format = '%({x-forwarded-for}i)s "%(r)s" %(s)s %(b)s %(M)sms'
