"""Attend que PostgreSQL accepte les connexions (utilisé par l'entrypoint)."""
import os
import sys
import time

import psycopg

url = os.environ.get("DATABASE_URL")
if not url:
    sys.exit("DATABASE_URL manquante")

for attempt in range(1, 61):
    try:
        psycopg.connect(url, connect_timeout=3).close()
        print("Base de données disponible.")
        break
    except Exception as exc:  # noqa: BLE001
        print(f"Attente de la base de données ({attempt}/60) : {type(exc).__name__}")
        time.sleep(2)
else:
    sys.exit("Base de données injoignable.")
