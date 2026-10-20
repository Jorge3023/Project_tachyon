"""Vistas de dashboard por archivo: validación de la configuración y utilidades comunes."""
from fastapi import HTTPException
import json
from servicios import dashboard as dash

MAX_VISTAS = 10

def nombre_vista(texto):
    n = " ".join((texto or "").split())
    if not 1 <= len(n) <= 40:
        raise HTTPException(status_code=422, detail="El nombre de la vista debe tener entre 1 y 40 caracteres")
    return n

def config_limpia(config, esquema):
    try:
        return dash.limpiar_config(config, esquema)
    except dash.ConfigInvalida as e:
        raise HTTPException(status_code=422, detail=str(e))

def vista_de(conn, a, vista_id):
    v = conn.execute("SELECT * FROM dashboards WHERE id=? AND archivo_id=?", (vista_id, a["id"])).fetchone()
    if not v:
        raise HTTPException(status_code=404, detail="Vista no encontrada")
    return v

def lista_vistas(conn, a):
    return [{"id": r["id"], "nombre": r["nombre"]} for r in
            conn.execute("SELECT id, nombre FROM dashboards WHERE archivo_id=? ORDER BY id", (a["id"],)).fetchall()]

def columnas_editor(a, esquema):
    """Columnas para el editor; las numéricas llevan su rango (para ofrecer latitud/longitud solo si encajan)."""
    try:
        res = {r["nombre"]: r for r in json.loads(a["resumen_json"] or "[]")}
    except ValueError:
        res = {}
    out = []
    for c in esquema:
        if c["rol"] == "ignorar":
            continue
        d = {"nombre": c["nombre"], "rol": c["rol"]}
        if c["rol"] == "numero" and res.get(c["nombre"], {}).get("min") is not None:
            d["min"], d["max"] = res[c["nombre"]]["min"], res[c["nombre"]]["max"]
        out.append(d)
    return out
