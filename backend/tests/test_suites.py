"""Ejecuta cada suite (suite_*.py) en su propio proceso: cada una configura su entorno y su base de datos.

  pytest backend/tests -v                          # SQLite (por defecto)
  TEST_PG_ADMIN_URL=postgresql://user:pass@host:5432/postgres pytest backend/tests -v
                                                   # además, cada suite contra su propia base PostgreSQL

Las suites también se pueden correr sueltas:  python backend/tests/suite_dashboard.py
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

AQUI = Path(__file__).resolve().parent
SUITES = sorted(AQUI.glob("suite_*.py"))
PG_ADMIN = os.getenv("TEST_PG_ADMIN_URL")


def _correr(suite, env_extra=None):
    env = {**os.environ, "PYTHONHASHSEED": "0", **(env_extra or {})}
    for k in ("DATABASE_URL", "SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_KEY"):
        if k not in (env_extra or {}):
            env.pop(k, None)
    r = subprocess.run([sys.executable, str(suite)], capture_output=True, text=True, timeout=1200, env=env)
    cola = "\n".join(r.stdout.splitlines()[-40:]) + "\n" + "\n".join(r.stderr.splitlines()[-15:])
    assert r.returncode == 0, f"{suite.name} falló:\n{cola}"


@pytest.mark.parametrize("suite", SUITES, ids=lambda p: p.stem.removeprefix("suite_"))
def test_sqlite(suite):
    _correr(suite)


@pytest.mark.skipif(not PG_ADMIN, reason="define TEST_PG_ADMIN_URL para probar contra PostgreSQL")
@pytest.mark.parametrize("suite", [s for s in SUITES if s.stem not in ("suite_detector", "suite_seed", "suite_storage_mock")],
                         ids=lambda p: p.stem.removeprefix("suite_"))
def test_postgres(suite):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    nombre = f"t_{suite.stem.removeprefix('suite_')}_{uuid.uuid4().hex[:6]}"
    with psycopg.connect(PG_ADMIN, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{nombre}" TEMPLATE template0 ENCODING \'UTF8\' LC_COLLATE \'C.UTF-8\' LC_CTYPE \'C.UTF-8\'')
    try:
        info = {**conninfo_to_dict(PG_ADMIN), "dbname": nombre}
        _correr(suite, {"DATABASE_URL": make_conninfo(**info)})
    finally:
        with psycopg.connect(PG_ADMIN, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)')
