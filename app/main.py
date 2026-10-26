import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.endpoints import (
    examenes,
    auth,
    administracion,
    postulantes,
    inscripciones,
    rostros,
    asignaciones,
    marcaciones,
    reportes
)

log = logging.getLogger(__name__)


def _precalentar_reconocimiento_facial():
    """Carga el modelo facial y los rostros habilitados al arrancar el servidor.

    Corre en un hilo aparte para no retrasar el inicio. Si insightface no está
    instalado, la API arranca igual (solo falla la parte facial).
    """
    try:
        from app.core.database import SessionLocal
        from app.services.face_service import face_service

        db = SessionLocal()
        try:
            face_service.precalentar(db)
        finally:
            db.close()
        log.info("Reconocimiento facial precalentado")
    except Exception:
        log.exception("No se pudo precalentar el reconocimiento facial")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=_precalentar_reconocimiento_facial, daemon=True).start()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(administracion.router, prefix=settings.API_V1_STR)
app.include_router(examenes.router, prefix="/api/v1")
app.include_router(postulantes.router, prefix=settings.API_V1_STR)
app.include_router(inscripciones.router, prefix=settings.API_V1_STR)
app.include_router(rostros.router, prefix=settings.API_V1_STR)
app.include_router(asignaciones.router, prefix=settings.API_V1_STR)
app.include_router(marcaciones.router, prefix=settings.API_V1_STR)
app.include_router(marcaciones.active_router, prefix=settings.API_V1_STR)
app.include_router(marcaciones.marking_router, prefix=settings.API_V1_STR)
app.include_router(reportes.router, prefix=settings.API_V1_STR)

@app.get("/health", tags=["Estado"])
def health_check():
    return {"status": "ok", "app": settings.PROJECT_NAME}