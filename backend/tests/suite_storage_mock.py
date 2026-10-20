"""datasets + permisos con el almacenamiento apuntando a un Supabase Storage falso."""
import os, sys
S = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, S)
REPO = os.path.abspath(os.path.join(S, "..", ".."))
import mock_supabase as M
srv, url = M.iniciar()
os.environ.update(SUPABASE_URL=url, SUPABASE_SECRET_KEY="sb_secret_prueba123", SUPABASE_BUCKET="datasets")
os.environ.pop("SUPABASE_SERVICE_KEY", None)
src = open(os.path.join(S, "suite_datasets.py"), encoding="utf-8").read()
src = src.replace('sys.exit(1 if fallos else 0)', 'pass')
exec(compile(src, "suite_datasets.py", "exec"))

print("\n-- comprobaciones propias del cliente de Supabase Storage")
check("modo de almacenamiento = supabase", main.storage.modo() == "supabase")
check("se hicieron peticiones HTTP al servidor falso", len(M.Estado.peticiones) > 5)
check("todas llevan cabecera apikey", all(h.get("apikey") == "sb_secret_prueba123" for _, _, h in M.Estado.peticiones))
check("clave nueva (sb_secret_) NO va como Bearer", all("Authorization" not in h and "authorization" not in h for _, _, h in M.Estado.peticiones))
check("lecturas usan /object/authenticated/", any(m == "GET" and "/object/authenticated/datasets/" in p for m, p, _ in M.Estado.peticiones))
check("subidas usan x-upsert", all(h.get("x-upsert") == "true" for m, _, h in M.Estado.peticiones if m == "POST"))
check("tras borrar todo no quedan objetos de dataset (solo quedan el compartido/otros)", not any(k.endswith(f"/datasets/{aid}.parquet") for k in M.Estado.objetos))
# diagnóstico
adm = login("admin@empresa.com", "admin123")
d = c.get("/admin/diagnostico", headers=adm).json()
check("diagnóstico: base y archivos OK", d["base_de_datos"]["ok"] and d["archivos"]["ok"], str(d))
check("diagnóstico solo admin", c.get("/admin/diagnostico", headers=ana).status_code == 403)
check("diagnóstico no deja basura", not any("salud/" in k for k in M.Estado.objetos))
# caída de Supabase => 503 limpio, sin 500 ni datos a medias
M.Estado.fallar = True
r = subir(ana, xl(ventas(30)))
check("Supabase caído => 503 con mensaje claro", r.status_code == 503 and "almacenamiento" in r.json()["detail"], r.text[:120])
check("no queda borrador huérfano en la lista", all(x["tipo"] != "generico" or x["estado"] != "borrador" for x in c.get("/archivos", headers=ana).json()))
check("diagnóstico informa el fallo", c.get("/admin/diagnostico", headers=adm).json()["archivos"]["ok"] is False)
M.Estado.fallar = False
r = subir(ana, xl(ventas(30))); check("al volver Supabase, sube normal", r.status_code == 200, r.text[:120])
# clave antigua (JWT) => también Bearer
main.storage.SUPABASE_KEY = "eyJhbGciOi.legacy.key"; M.Estado.peticiones.clear(); main.storage.put("x/y.txt", b"1")
h = M.Estado.peticiones[-1][2]
check("clave antigua (eyJ...) va en apikey y Bearer", h.get("apikey") == "eyJhbGciOi.legacy.key" and h.get("Authorization") == "Bearer eyJhbGciOi.legacy.key")
# rutas peligrosas
try:
    main.storage.put("../etc/passwd", b"x"); check("ruta con .. rechazada", False)
except main.storage.ErrorAlmacenamiento: check("ruta con .. rechazada", True)
print(); print("RESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
