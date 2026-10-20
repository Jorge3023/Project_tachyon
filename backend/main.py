"""API de Tachyon: crea la aplicación, configura CORS y registra los routers.

Estructura del backend:
  core/       base de datos, almacenamiento, sesiones, permisos y migraciones
  servicios/  lógica de datos sin HTTP: detector de columnas, motor de dashboards, exportación, lectura de Parquet
  routers/    endpoints agrupados por tema (cada archivo es un APIRouter)
"""
import os
import warnings

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core import db, storage
from core.config import ORIGENES_PERMITIDOS
from core.migraciones import init_db
from routers import (admin, archivos, auth, compartir, dashboards, datasets, exportacion,
                     plantillas, principal, proyectos)

app = FastAPI(title="Tachyon API")

# La autenticación va en el header Authorization (JWT), así que no se necesitan cookies/credenciales.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENES_PERMITIDOS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Filas-Exportadas", "X-Exportacion-Truncada"],
)

for modulo in (auth, archivos, proyectos, compartir, admin, datasets, dashboards, exportacion, principal, plantillas):
    app.include_router(modulo.router)


@app.get("/")
def read_root():
    return {"estado": "En línea", "mensaje": "API de Tachyon funcionando correctamente",
            "base_de_datos": db.motor(), "archivos": storage.modo()}


@app.on_event("shutdown")
def _al_apagar():
    db.cerrar()


@app.exception_handler(storage.ErrorAlmacenamiento)
def _error_almacenamiento(request, exc):
    print(f"=== Error de almacenamiento: {exc} ===")
    return JSONResponse(status_code=503, content={"detail": "El almacenamiento de archivos no está disponible. Intenta de nuevo en un momento."})


# En hosts con disco efímero (Render) SQLite y el disco local se pierden al reiniciar.
if os.getenv("RENDER") and (not db.ES_POSTGRES or not storage.ES_SUPABASE):
    warnings.warn("Estás en Render sin DATABASE_URL y/o SUPABASE_URL+SUPABASE_SECRET_KEY: los datos se perderán "
                  "cuando el servicio se reinicie. Configura Supabase (ver README).")

init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
