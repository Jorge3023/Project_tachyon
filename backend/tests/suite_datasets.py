"""Pruebas de datasets genéricos. Uso: python3 -I test_datasets.py <repo>"""
import io, os, sys, tempfile
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from datetime import datetime, timedelta
repo = REPO
sys.path.insert(0, os.path.join(repo, "backend"))
wd = tempfile.mkdtemp(prefix="tachyon_ds_"); os.chdir(wd)
os.environ["SEED_DEMO_USERS"] = "1"
import numpy as np, pandas as pd
from fastapi.testclient import TestClient
import main
from routers import datasets as ds_router
c = TestClient(main.app, raise_server_exceptions=False)
fallos = []
def check(n, cond, extra=""):
    print(("OK    " if cond else "FALLA ") + n + (f"  -> {extra}" if (extra and not cond) else ""))
    if not cond: fallos.append(n)
def login(correo, pw):
    r = c.post("/auth/login", data={"username": correo, "password": pw})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
ana = login("mrodriguez@empresa.com", "operador123")
otro = login("cmendez@empresa.com", "operador123")

np.random.seed(1); N = 120
def ventas(n=N, extra_col=False):
    d = pd.DataFrame({"Fecha": [datetime(2026,1,1)+timedelta(days=i%60) for i in range(n)],
        "Cliente": np.random.choice(list("ABCDE"), n), "Monto": np.round(np.random.uniform(10, 999, n), 2),
        "Estatus": np.random.choice(["Pagado","Pendiente"], n), "Folio": [f"F-{i:04d}" for i in range(n)]})
    if extra_col: d["Notas"] = "x"
    return d
def xl(df, startrow=0):
    b = io.BytesIO(); df.to_excel(b, index=False, startrow=startrow); return b.getvalue()
XL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
def subir(h, datos, nombre="ventas.xlsx", tipo=XL):
    return c.post("/datasets/analizar", headers=h, files={"file": (nombre, datos, tipo)})

check("sin token => 401", c.post("/datasets/analizar", files={"file": ("a.csv", b"a,b\n1,2")}).status_code == 401)
r = subir(ana, xl(ventas(), startrow=2))
check("analizar xlsx con títulos arriba", r.status_code == 200, r.text[:200])
a = r.json(); aid = a["archivo_id"]
check("detecta encabezado (filas en blanco no cuentan) y 120 filas", a["fila_encabezado"] == 0 and a["filas"] == N, str(a["fila_encabezado"]))
roles = {x["nombre"]: x["rol"] for x in a["columnas"]}
check("roles detectados", roles == {"Fecha":"fecha","Cliente":"categoria","Monto":"numero","Estatus":"estado","Folio":"identificador"}, str(roles))
check("trae vista previa y roles disponibles", len(a["vista_previa"]["filas"]) == 8 and "ignorar" in a["roles"])
check("sin plantilla la primera vez", a["plantilla"] is None)
check("borrador NO aparece en la lista", all(x["id"] != aid for x in c.get("/archivos", headers=ana).json()))
check("otro usuario no puede re-analizar mi borrador", c.get(f"/datasets/{aid}/analisis", headers=otro).status_code == 404)
check("otro usuario no puede confirmar mi borrador", c.post(f"/datasets/{aid}/confirmar", headers=otro, json={"columnas": [{"nombre":"Fecha","rol":"fecha"}]}).status_code == 404)
r = c.get(f"/datasets/{aid}/analisis?fila_encabezado=1", headers=ana)
check("re-analizar con otra fila funciona", r.status_code == 200 and r.json()["fila_encabezado"] == 1, r.text[:150])

cols = [{"nombre": x["nombre"], "rol": x["rol"], "nombre_mostrar": x["nombre"]} for x in a["columnas"]]
check("rol inválido => 422", c.post(f"/datasets/{aid}/confirmar", headers=ana, json={"columnas": [{"nombre":"Fecha","rol":"magia"}]}).status_code == 422)
check("todas ignoradas => 422", c.post(f"/datasets/{aid}/confirmar", headers=ana, json={"columnas": [{"nombre":"Fecha","rol":"ignorar"}]}).status_code == 422)
cols_mod = [dict(x) for x in cols]
for x in cols_mod:
    if x["nombre"] == "Monto": x["nombre_mostrar"] = "Venta total"
    if x["nombre"] == "Folio": x["rol"] = "ignorar"
r = c.post(f"/datasets/{aid}/confirmar", headers=ana, json={"fila_encabezado": 0, "columnas": cols_mod, "guardar_plantilla": True, "nombre_plantilla": "Ventas mensuales"})
check("confirmar con renombre e ignorar", r.status_code == 200 and r.json()["filas"] == N and r.json()["plantilla_guardada"], r.text[:200])
check("el borrador ya no se puede confirmar otra vez", c.post(f"/datasets/{aid}/confirmar", headers=ana, json={"columnas": cols}).status_code == 404)
check("se borró el original temporal", not main.storage.existe(f"borradores/{aid}.src"))
check("el dataset limpio quedó guardado (parquet)", main.storage.existe(f"datasets/{aid}.parquet"))

lista = c.get("/archivos", headers=ana).json()
it = [x for x in lista if x["id"] == aid]
check("aparece en la lista como generico/procesado", len(it) == 1 and it[0]["tipo"] == "generico" and it[0]["estado"] == "procesado" and it[0]["filas"] == N, str(it))
r = c.get(f"/datasets/{aid}/datos?por_pagina=10", headers=ana)
d = r.json()
check("ver datos: 200, columnas y paginación", r.status_code == 200 and d["total"] == N and len(d["filas"]) == 10 and [x["nombre"] for x in d["columnas"]] == ["Fecha","Cliente","Venta total","Estatus"], r.text[:200])
check("fechas formateadas", d["filas"][0][0] == "2026-01-01", str(d["filas"][0]))
rs = {x["nombre"]: x for x in d["resumen"]}
check("resumen numérico y de fecha", "suma" in rs["Venta total"] and rs["Fecha"]["desde"] == "2026-01-01" and rs["Cliente"]["unicos"] == 5, str(rs))
check("página 2 distinta", c.get(f"/datasets/{aid}/datos?por_pagina=10&pagina=2", headers=ana).json()["filas"][0] != d["filas"][0])
check("privado: otro usuario 404", c.get(f"/datasets/{aid}/datos", headers=otro).status_code == 404)

# plantilla reutilizada
r = subir(ana, xl(ventas(60, extra_col=True)))
a2 = r.json()
check("2º archivo con mismas columnas (+1 extra) reconoce la plantilla", a2["plantilla"] and a2["plantilla"]["nombre"] == "Ventas mensuales", str(a2.get("plantilla")))
rn = {x["nombre"]: x["nombre_mostrar"] for x in a2["columnas"]}
check("la plantilla aplica el renombre", rn["Monto"] == "Venta total", str(rn))
check("plantilla es privada: otro no la ve", subir(otro, xl(ventas(60))).json()["plantilla"] is None)
check("lista de plantillas", [p["nombre"] for p in c.get("/plantillas", headers=ana).json()] == ["Ventas mensuales"])
check("otro no ve plantillas ajenas", c.get("/plantillas", headers=otro).json() == [])
c.delete(f"/datasets/{a2['archivo_id']}/borrador", headers=ana)
check("cancelar borrador lo elimina", not main.storage.existe(f"borradores/{a2['archivo_id']}.src"))

# compartir
check("otro no ve antes de compartir", c.get(f"/datasets/{aid}/datos", headers=otro).status_code == 404)
c.post(f"/archivos/{aid}/comparticiones", headers=ana, json={"correo": "cmendez@empresa.com"})
check("compartido por correo => puede ver datos", c.get(f"/datasets/{aid}/datos", headers=otro).status_code == 200)
check("compartido no puede borrar", c.delete(f"/archivos/{aid}", headers=otro).status_code == 404)

# CSV europeo latin-1
csv = "Fecha;Total;Sucursal\n01/02/2026;1.234,50;Mérida\n02/02/2026;99,9;Puebla\n".encode("latin-1")
r = subir(ana, csv, "x.csv", "text/csv"); j = r.json()
check("CSV ; latin-1 con coma decimal", r.status_code == 200 and {x["nombre"]: x["rol"] for x in j["columnas"]}["Total"] == "numero", r.text[:200])
r = c.post(f"/datasets/{j['archivo_id']}/confirmar", headers=ana, json={"columnas": [{"nombre": x["nombre"], "rol": x["rol"]} for x in j["columnas"]]})
dd = c.get(f"/datasets/{j['archivo_id']}/datos", headers=ana).json()
check("CSV limpio: 1.234,50 -> 1234.5 y fecha dd/mm", dd["filas"][0][1] == 1234.5 and dd["filas"][0][0] == "2026-02-01", str(dd["filas"]))

# errores
check("archivo vacío => 422", subir(ana, b"", "v.csv", "text/csv").status_code == 422)
check("archivo basura => 422", subir(ana, b"\x00\x01\x02\xff" * 50, "raro.xlsx").status_code == 422)
check("tipo no soportado => 422", subir(ana, b"hola", "a.pdf", "application/pdf").status_code == 422)
ds_router.MAX_BYTES_DATASET = 100
check("archivo demasiado grande => 413", subir(ana, b"a,b\n" + b"1,2\n" * 100, "g.csv", "text/csv").status_code == 413)
ds_router.MAX_BYTES_DATASET = 25*1024*1024
check("no quedan borradores huérfanos tras errores", len(c.get("/archivos", headers=ana).json()) == 2)

# borrar limpia archivos
check("dueño borra dataset", c.delete(f"/archivos/{aid}", headers=ana).status_code == 200)
check("se borró el parquet", not main.storage.existe(f"datasets/{aid}.parquet"))
check("el compartido ya no accede", c.get(f"/datasets/{aid}/datos", headers=otro).status_code == 404)

print(); print("RESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
