"""Arranque: sin cuentas de demostración por defecto y creación segura del administrador inicial."""
import os, sys, tempfile, warnings
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
repo = REPO; sys.path.insert(0, os.path.join(repo, "backend")); os.chdir(tempfile.mkdtemp())
os.environ.pop("SEED_DEMO_USERS", None); os.environ["ADMIN_EMAIL"] = "Jefe@Empresa.com"; os.environ["ADMIN_PASSWORD"] = "corta"
from fastapi.testclient import TestClient
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always"); import main
    msgs = " | ".join(str(x.message) for x in w)
c = TestClient(main.app)
login = lambda u, p: c.post("/auth/login", data={"username": u, "password": p}).status_code
fallos = []
def check(nombre, cond):
    print(("OK    " if cond else "FALLA ") + nombre)
    if not cond: fallos.append(nombre)
check("sin demo por defecto", login("admin@empresa.com", "admin123") == 401)
check("contraseña corta no crea admin + avisa", login("jefe@empresa.com", "corta") == 401 and "menos de 8" in msgs and "ningún usuario" in msgs)
os.environ["ADMIN_PASSWORD"] = "clave-larga-123"; main.init_db()
check("admin con 8+ caracteres entra (correo normalizado)", login("jefe@empresa.com", "clave-larga-123") == 200)
print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
