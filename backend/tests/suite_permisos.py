"""Pruebas de usuarios, privacidad y compartir. Uso: python3 -I test_permisos.py <repo>"""
import io, os, sys, tempfile
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from datetime import datetime, timedelta

repo = REPO
sys.path.insert(0, os.path.join(repo, "backend"))
os.chdir(tempfile.mkdtemp(prefix="tachyon_perm_"))
os.environ["SEED_DEMO_USERS"] = "1"

import pandas as pd
from fastapi.testclient import TestClient
import main

c = TestClient(main.app, raise_server_exceptions=False)
fallos = []

def check(nombre, cond, extra=""):
    print(("OK    " if cond else "FALLA ") + nombre + (f"  -> {extra}" if (extra and not cond) else ""))
    if not cond: fallos.append(nombre)

def login(correo, pw):
    r = c.post("/auth/login", data={"username": correo, "password": pw})
    return r, {"Authorization": f"Bearer {r.json().get('access_token','')}"}

def crear(h):
    """Sube un CSV pequeño, acepta las columnas detectadas y devuelve el id (o None si algo falla)."""
    filas = ["Fecha,Cliente,Monto"] + [f"2026-01-{(i % 28) + 1:02d},{'ABC'[i % 3]},{10 + i}" for i in range(20)]
    r = c.post("/datasets/analizar", headers=h, files={"file": ("ventas.csv", "\n".join(filas).encode(), "text/csv")})
    if r.status_code != 200: return None
    a = r.json()
    r = c.post(f"/datasets/{a['archivo_id']}/confirmar", headers=h,
               json={"fila_encabezado": a["fila_encabezado"], "columnas": [{"nombre": x["nombre"], "rol": x["rol"], "nombre_mostrar": x["nombre"]} for x in a["columnas"]]})
    return a["archivo_id"] if r.status_code == 200 else None

# ── Admin crea usuario ───────────────────────────────────────────────────────
r, adm = login("admin@empresa.com", "admin123")
check("admin entra", r.status_code == 200)
check("admin sin username => necesita_username", r.json()["usuario"]["necesita_username"] is True)

r = c.post("/usuarios", headers=adm, json={"correo": "Ana@Empresa.com", "password": "corta"})
check("contraseña corta rechazada", r.status_code == 422)
r = c.post("/usuarios", headers=adm, json={"correo": "ana@empresa.com", "password": "clave-segura-1"})
check("admin crea usuario", r.status_code == 200 and r.json()["pendiente_username"] is True, r.text)
r = c.post("/usuarios", headers=adm, json={"correo": "ANA@empresa.com", "password": "clave-segura-1"})
check("correo duplicado (sin importar mayúsculas) rechazado", r.status_code == 409)
r, nopriv = login("mrodriguez@empresa.com", "operador123")
check("operador no puede crear usuarios", c.post("/usuarios", headers=nopriv,
      json={"correo": "x@y.com", "password": "12345678"}).status_code == 403)

# ── Primer ingreso: username ─────────────────────────────────────────────────
r, ana = login("ana@empresa.com", "clave-segura-1")
check("usuario nuevo entra con correo/contraseña", r.status_code == 200)
check("usuario nuevo debe elegir username", r.json()["usuario"]["necesita_username"] is True)
check("username inválido rechazado", c.post("/auth/username", headers=ana, json={"username": "a b"}).status_code == 422)
r = c.post("/auth/username", headers=ana, json={"username": "ana.gl"})
check("username válido aceptado", r.status_code == 200 and r.json()["necesita_username"] is False, r.text)
check("/auth/me refleja username", c.get("/auth/me", headers=ana).json()["nombre"] == "ana.gl")
check("no se puede cambiar el username después", c.post("/auth/username", headers=ana, json={"username": "otro_nombre"}).status_code == 409)
r, adm_h = login("admin@empresa.com", "admin123")
r = c.post("/auth/username", headers=adm_h, json={"username": "ANA.GL"})
check("username único sin importar mayúsculas", r.status_code == 409)

# ── Privacidad de archivos ───────────────────────────────────────────────────
aid = crear(ana)
check("usuario normal puede subir un archivo", aid is not None)
r, maria = login("mrodriguez@empresa.com", "operador123")
check("otro usuario NO ve el archivo en su lista", all(a["id"] != aid for a in c.get("/archivos", headers=maria).json()))
check("admin tampoco ve archivos ajenos", all(a["id"] != aid for a in c.get("/archivos", headers=adm_h).json()))
check("datos ajenos => 404", c.get(f"/datasets/{aid}/datos", headers=maria).status_code == 404)
check("el administrador tampoco ve datos ajenos", c.get(f"/datasets/{aid}/datos", headers=adm_h).status_code == 404)
check("re-analizar o confirmar lo ajeno => 404", c.post(f"/datasets/{aid}/confirmar", headers=maria, json={"columnas": [{"nombre": "Fecha", "rol": "fecha"}]}).status_code == 404)
check("borrado ajeno => 404", c.delete(f"/archivos/{aid}", headers=maria).status_code == 404)
check("compartir archivo ajeno => 404", c.post(f"/archivos/{aid}/comparticiones", headers=maria, json={"correo": "x@y.com"}).status_code == 404)
r = c.get(f"/datasets/{aid}/datos", headers=ana)
check("el dueño sí ve sus datos", r.status_code == 200 and r.json()["total"] == 20, r.text[:120])
la = c.get("/archivos", headers=ana).json()
check("dueño ve es_mio y num_compartidos", la[0]["es_mio"] is True and la[0]["num_compartidos"] == 0, str(la))
check("lista no filtra el JSON pesado", "reporte_json" not in la[0])

# ── Compartir por correo ─────────────────────────────────────────────────────
check("correo inválido rechazado", c.post(f"/archivos/{aid}/comparticiones", headers=ana, json={"correo": "nope"}).status_code == 422)
check("no se comparte consigo mismo", c.post(f"/archivos/{aid}/comparticiones", headers=ana, json={"correo": "ANA@empresa.com"}).status_code == 422)
r = c.post(f"/archivos/{aid}/comparticiones", headers=ana, json={"correo": "  MRodriguez@Empresa.com "})
check("compartir con María (correo normalizado)", r.status_code == 200, r.text)
c.post(f"/archivos/{aid}/comparticiones", headers=ana, json={"correo": "mrodriguez@empresa.com"})
check("compartir 2 veces no duplica", len(c.get(f"/archivos/{aid}/comparticiones", headers=ana).json()) == 1)
lm = c.get("/archivos", headers=maria).json()
check("María ve el archivo compartido (es_mio False)", len(lm) == 1 and lm[0]["es_mio"] is False and lm[0]["subido_por_nombre"] == "ana.gl", str(lm))
check("María no ve con quién se comparte", lm[0]["num_compartidos"] is None)
check("filtro origen=mios vacío para María", c.get("/archivos?origen=mios", headers=maria).json() == [])
check("filtro origen=compartidos tiene 1", len(c.get("/archivos?origen=compartidos", headers=maria).json()) == 1)
r = c.get(f"/datasets/{aid}/datos", headers=maria)
check("María ve los datos compartidos (solo lectura)", r.status_code == 200 and r.json()["total"] == 20 and r.json()["archivo"]["es_mio"] is False, r.text[:120])
check("María no puede borrar lo compartido", c.delete(f"/archivos/{aid}", headers=maria).status_code == 404)
check("María no ve la lista de compartidos", c.get(f"/archivos/{aid}/comparticiones", headers=maria).status_code == 404)
check("María no puede re-compartir", c.post(f"/archivos/{aid}/comparticiones", headers=maria, json={"correo": "cmendez@empresa.com"}).status_code == 404)
r, carlos = login("cmendez@empresa.com", "operador123")
check("Carlos (no compartido) sigue sin ver nada", c.get("/archivos", headers=carlos).json() == [])

# compartir con alguien que aún no tiene cuenta
c.post(f"/archivos/{aid}/comparticiones", headers=ana, json={"correo": "nuevo@empresa.com"})
c.post("/usuarios", headers=adm_h, json={"correo": "nuevo@empresa.com", "password": "otra-clave-123"})
r, nuevo = login("nuevo@empresa.com", "otra-clave-123")
check("quien se registra después ve lo que se compartió con su correo", len(c.get("/archivos", headers=nuevo).json()) == 1)

# dejar de compartir
r = c.delete(f"/archivos/{aid}/comparticiones/mrodriguez@empresa.com", headers=ana)
check("dueño deja de compartir", r.status_code == 200)
check("María ya no lo ve", c.get("/archivos", headers=maria).json() == [])
check("ni sus datos", c.get(f"/datasets/{aid}/datos", headers=maria).status_code == 404)

# ── Desactivar usuario / borrar archivo ──────────────────────────────────────
uid = [x for x in c.get("/usuarios", headers=adm_h).json() if x["correo"] == "ana@empresa.com"][0]["id"]
check("admin no se desactiva a sí mismo", c.patch(f"/usuarios/{[x for x in c.get('/usuarios', headers=adm_h).json() if x['correo']=='admin@empresa.com'][0]['id']}", headers=adm_h, json={"activo": False}).status_code == 422)
check("admin ve pendiente_username", [x for x in c.get("/usuarios", headers=adm_h).json() if x["correo"] == "nuevo@empresa.com"][0]["pendiente_username"] is True)
check("dueño borra su archivo", c.delete(f"/archivos/{aid}", headers=ana).status_code == 200)
check("el compartido a 'nuevo' desaparece", c.get("/archivos", headers=nuevo).json() == [])
check("admin desactiva usuario", c.patch(f"/usuarios/{uid}", headers=adm_h, json={"activo": False}).status_code == 200)
check("usuario desactivado no puede entrar", login("ana@empresa.com", "clave-segura-1")[0].status_code == 401)
check("token de usuario desactivado deja de servir", c.get("/auth/me", headers=ana).status_code == 401)

print()
print("RESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
