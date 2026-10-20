"""Pruebas del cambio de almacenamiento (reportes en Parquet + lectura por páginas).
Uso: python3 -I test_almacenamiento.py <ruta_abs_repo>   (usa DATABASE_URL/SUPABASE_* si están definidas)"""
import io, os, sys, tempfile, json
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from datetime import datetime, timedelta
repo = os.path.abspath(REPO); sys.path.insert(0, os.path.join(repo, "backend"))
os.chdir(tempfile.mkdtemp(prefix="tachyon_alm_")); os.environ["SEED_DEMO_USERS"] = "1"
import numpy as np, pandas as pd
from fastapi.testclient import TestClient
import main
from core.db import get_db
c = TestClient(main.app, raise_server_exceptions=False)
fallos = []
def check(n, cond, extra=""):
    print(("OK    " if cond else "FALLA ") + n + (f"  -> {extra}" if (extra and not cond) else ""))
    if not cond: fallos.append(n)
def login(u, p):
    r = c.post("/auth/login", data={"username": u, "password": p}); return {"Authorization": f"Bearer {r.json()['access_token']}"}
adm = login("admin@empresa.com", "admin123"); ana = login("mrodriguez@empresa.com", "operador123")
XL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# ── 1. Dataset grande: varias páginas y varios grupos de filas ─────────────────
N = 25_037
np.random.seed(3)
df = pd.DataFrame({"Fecha": [datetime(2026,1,1) + timedelta(hours=i) for i in range(N)],
                   "Cliente": np.random.choice(list("ABCDE"), N), "Monto": np.round(np.random.uniform(1, 500, N), 2),
                   "Folio": [f"F-{i:06d}" for i in range(N)]})
csv = df.to_csv(index=False).encode()
r = c.post("/datasets/analizar", headers=ana, files={"file": ("grande.csv", csv, "text/csv")}); a = r.json(); aid = a["archivo_id"]
cols = [{"nombre": x["nombre"], "rol": x["rol"], "nombre_mostrar": x["nombre"]} for x in a["columnas"]]
r = c.post(f"/datasets/{aid}/confirmar", headers=ana, json={"fila_encabezado": 0, "columnas": cols})
check("confirmar dataset de 25 037 filas", r.status_code == 200 and r.json()["filas"] == N, r.text[:150])
import pyarrow.parquet as pq
pf = pq.ParquetFile(io.BytesIO(main.storage.get(f"datasets/{aid}.parquet")))
check("el Parquet se escribió en grupos de 10 000 filas", pf.metadata.num_row_groups == 3, str(pf.metadata.num_row_groups))
conn = get_db(); fila = conn.execute("SELECT resumen_json FROM archivos WHERE id=?", (aid,)).fetchone(); conn.close()
check("el resumen por columna se guardó al confirmar", bool(fila["resumen_json"]) and len(json.loads(fila["resumen_json"])) == 4)
def pagina(p, pp=50):
    r = c.get(f"/datasets/{aid}/datos?pagina={p}&por_pagina={pp}", headers=ana); return r.status_code, (r.json() if r.status_code == 200 else None)
def folios(j): return [f[3] for f in j["filas"]]
esperado = lambda ini, n: list(df["Folio"].iloc[ini:ini+n])
for p, pp in [(1, 50), (2, 50), (200, 50), (201, 50), (500, 50), (501, 50), (1, 200), (50, 200), (51, 200), (126, 200)]:
    st, j = pagina(p, pp); ini = (p-1)*pp
    check(f"página {p} (de {pp}) trae las filas correctas", st == 200 and folios(j) == esperado(ini, pp) and j["total"] == N,
          str(folios(j)[:2]) if j else str(st))
st, j = pagina(600, 50)  # 600*50 = 30000 > N
check("página más allá del final => vacía, total correcto", st == 200 and j["filas"] == [] and j["total"] == N)
st, j = pagina(1)
check("las fechas salen formateadas", j["filas"][0][0] == "2026-01-01" and j["filas"][1][0] == "2026-01-01 01:00", str(j["filas"][:2]))
check("el resumen coincide con el cálculo completo", abs([x for x in j["resumen"] if x["nombre"] == "Monto"][0]["suma"] - float(df["Monto"].sum())) < 0.01)
# ── 2. Respaldo: dataset sin resumen guardado (versión anterior) ───────────────
conn = get_db(); conn.execute("UPDATE archivos SET resumen_json=NULL WHERE id=?", (aid,)); conn.commit(); conn.close()
st, j2 = pagina(1)
check("sin resumen guardado se calcula al vuelo y coincide", st == 200 and j2["resumen"] == j["resumen"])
# ── 3. Borrar limpia el Storage ───────────────────────────────────────────────
check("borrar dataset genérico", c.delete(f"/archivos/{aid}", headers=ana).status_code == 200 and not main.storage.existe(f"datasets/{aid}.parquet"))
# ── 4. Ya no existe el flujo de producción (SMT) ──────────────────────────────
check("/archivos/upload eliminado", c.post("/archivos/upload", headers=ana).status_code in (404, 405))
check("/dashboard/resumen eliminado", c.get("/dashboard/resumen", headers=ana).status_code == 404)
check("/archivos/{id}/reporte eliminado", c.get(f"/archivos/{aid}/reporte", headers=ana).status_code in (404, 405))
check("el listado no trae linea/equipo", all("linea" not in x and "equipo" not in x for x in c.get("/archivos", headers=ana).json()))
conn = get_db(); uid = conn.execute("SELECT id FROM usuarios WHERE correo=?", ("mrodriguez@empresa.com",)).fetchone()["id"]
conn.execute("INSERT INTO archivos (nombre, estado, tipo, subido_por, filas) VALUES (?,?,?,?,?)", ("viejo.xlsx", "procesado", "produccion", uid, 5)); conn.commit(); conn.close()
check("los archivos antiguos de producción ya no se listan", "viejo.xlsx" not in [x["nombre"] for x in c.get("/archivos", headers=ana).json()])
print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
