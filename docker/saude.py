"""Verificação de saúde do contêiner: /saude responde 200 (banco acessível e schema em dia)."""
import sys
import urllib.request

try:
    with urllib.request.urlopen("http://127.0.0.1:8000/saude", timeout=8) as r:
        sys.exit(0 if r.status == 200 else 1)
except Exception:  # noqa: BLE001  (inclui 503: urllib lança erro para 4xx/5xx)
    sys.exit(1)
