"""Espera o PostgreSQL ficar pronto antes de migrar e subir o app. Usa só variáveis de ambiente (DATABASE_URL)."""
import os
import sys
import time

import psycopg

LIMITE_S = int(os.environ.get("AGUARDAR_SEGUNDOS", "90"))

inicio = time.time()
while True:
    try:
        psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5).close()
        print("[espera] PostgreSQL: ok")
        break
    except Exception as erro:  # noqa: BLE001
        if time.time() - inicio > LIMITE_S:
            print(f"[espera] PostgreSQL não ficou pronto em {LIMITE_S}s ({erro})", file=sys.stderr)
            sys.exit(1)
        time.sleep(2)
