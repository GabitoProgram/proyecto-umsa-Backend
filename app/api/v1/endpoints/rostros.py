import cv2
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, ConfigDict
from datetime import datetime

from app.core.database import get_db
from app.api.deps import get_current_user, registrar_auditoria
from app.models.usuario import Usuario
from app.models.postulante import Postulante, EstadoBiometria
from app.models.biometria import Rostro, Huella
from app.services.face_service import face_service

router = APIRouter(prefix="/rostros", tags=["Reconocimiento Facial"])

SIMILITUD_UMBRAL_DEFAULT = 0.50  # Umbral estándar de InsightFace buffalo_s


class HuellaOut(BaseModel):
    id_huella: int
    tipo_dedo: int
    habilitada: bool
    fecha_registro: datetime
    model_config = ConfigDict(from_attributes=True)


def actualizar_estado_biometria(db: Session, postulante: Postulante):
    tiene_rostro = db.query(Rostro).filter(
        Rostro.id_postulante == postulante.id_postulante,
        Rostro.habilitada.is_(True)
    ).first() is not None
    total_huellas = db.query(func.count(Huella.id_huella)).filter(
        Huella.id_postulante == postulante.id_postulante
    ).scalar() or 0
    if tiene_rostro and total_huellas == 10:
        postulante.estado_biometria = EstadoBiometria.COMPLETO
    elif tiene_rostro or total_huellas:
        postulante.estado_biometria = EstadoBiometria.INCOMPLETO
    else:
        postulante.estado_biometria = EstadoBiometria.PENDIENTE

@router.post("/{id_postulante}/registrar")
def registrar_rostro(
    id_postulante: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user)
):
    postulante = db.query(Postulante).filter(Postulante.id_postulante == id_postulante).first()
    if not postulante:
        raise HTTPException(status_code=404, detail="Postulante no encontrado")

    contents = file.file.read()
    img_bgr = face_service.procesar_imagen_bytes(contents)
    if img_bgr is None:
        raise HTTPException(status_code=400, detail="Formato de imagen inválido o archivo corrupto")

    embedding, bbox = face_service.extraer_embedding(img_bgr)
    if embedding is None:
        raise HTTPException(status_code=400, detail="No se detectó ningún rostro en la imagen")

    # El administrador debe habilitar el rostro antes del examen.
    db.query(Rostro).filter(Rostro.id_postulante == id_postulante).update({"habilitada": False})

    # Guardar nuevo rostro activo
    nuevo_rostro = Rostro(
        id_postulante=id_postulante,
        embedding=embedding,
        imagen_captura=contents,
        habilitada=False
    )
    db.add(nuevo_rostro)

    actualizar_estado_biometria(db, postulante)

    db.commit()
    face_service.invalidar_cache()
    registrar_auditoria(
        db, admin.id_usuario, "REGISTRO_FACIAL", "rostros",
        f"Postulante {postulante.ci} - Estado Biometría: {postulante.estado_biometria}"
    )

    return {
        "status": "ok",
        "mensaje": "Rostro registrado correctamente",
        "id_postulante": id_postulante,
        "estado_biometria": postulante.estado_biometria
    }


@router.get("/{id_postulante}/imagen")
def obtener_imagen_rostro(
    id_postulante: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    rostro = db.query(Rostro).filter(
        Rostro.id_postulante == id_postulante,
    ).order_by(Rostro.fecha_registro.desc()).first()
    if not rostro or not rostro.imagen_captura:
        raise HTTPException(status_code=404, detail="El postulante no tiene foto")

    return Response(
        content=bytes(rostro.imagen_captura),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/{id_postulante}/huellas", response_model=List[HuellaOut])
def listar_huellas(
    id_postulante: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user)
):
    return db.query(Huella).filter(
        Huella.id_postulante == id_postulante
    ).order_by(Huella.tipo_dedo).all()


@router.post("/{id_postulante}/huellas/{tipo_dedo}", response_model=HuellaOut)
def registrar_huella(
    id_postulante: int,
    tipo_dedo: int,
    file: UploadFile = File(...),
    habilitada: bool = Form(False),
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user)
):
    import logging
    logger = logging.getLogger(__name__)
    logger.info("POST huella: id_postulante=%s, tipo_dedo=%s, habilitada=%s", id_postulante, tipo_dedo, habilitada)
    
    if not 1 <= tipo_dedo <= 10:
        raise HTTPException(status_code=422, detail="tipo_dedo debe estar entre 1 y 10")
    postulante = db.query(Postulante).filter(Postulante.id_postulante == id_postulante).first()
    if not postulante:
        raise HTTPException(status_code=404, detail="Postulante no encontrado")
    contenido = file.file.read()
    logger.info("Plantilla recibida: %d bytes", len(contenido))
    if not contenido:
        raise HTTPException(status_code=400, detail="La plantilla de huella está vacía")

    huella = db.query(Huella).filter(
        Huella.id_postulante == id_postulante,
        Huella.tipo_dedo == tipo_dedo
    ).first()
    if huella:
        logger.info("Actualizando huella existente id_huella=%s", huella.id_huella)
        huella.plantilla_biometrica = contenido
        huella.habilitada = habilitada
        huella.habilitada_por = admin.id_usuario if habilitada else None
    else:
        logger.info("Creando nueva huella para id_postulante=%s, tipo_dedo=%s", id_postulante, tipo_dedo)
        huella = Huella(
            id_postulante=id_postulante,
            tipo_dedo=tipo_dedo,
            plantilla_biometrica=contenido,
            habilitada=habilitada,
            habilitada_por=admin.id_usuario if habilitada else None
        )
        db.add(huella)

    actualizar_estado_biometria(db, postulante)
    db.commit()
    db.refresh(huella)
    registrar_auditoria(
        db,
        admin.id_usuario,
        "REGISTRO_HUELLA",
        "huellas",
        f"Postulante {postulante.ci}, dedo {tipo_dedo}"
    )
    logger.info("Huella guardada exitosamente, id_huella=%s", huella.id_huella)
    return huella


class RostroOut(BaseModel):
    id_rostro: int
    id_postulante: int
    habilitada: bool
    fecha_registro: datetime
    model_config = ConfigDict(from_attributes=True)


@router.patch("/{id_rostro}/habilitada", response_model=RostroOut)
def cambiar_estado_rostro(
    id_rostro: int,
    habilitada: bool,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user)
):
    rostro = db.query(Rostro).filter(Rostro.id_rostro == id_rostro).first()
    if not rostro:
        raise HTTPException(status_code=404, detail="Rostro no encontrado")
    rostro.habilitada = habilitada
    rostro.habilitada_por = admin.id_usuario if habilitada else None
    db.commit()
    face_service.invalidar_cache()
    db.refresh(rostro)
    registrar_auditoria(
        db, admin.id_usuario, "CAMBIAR_ESTADO_ROSTRO", "rostros",
        f"Rostro {id_rostro}: habilitada={habilitada}"
    )
    return rostro


@router.patch("/huellas/{id_huella}/habilitada", response_model=HuellaOut)
def cambiar_estado_huella(
    id_huella: int,
    habilitada: bool,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user)
):
    huella = db.query(Huella).filter(Huella.id_huella == id_huella).first()
    if not huella:
        raise HTTPException(status_code=404, detail="Huella no encontrada")
    huella.habilitada = habilitada
    huella.habilitada_por = admin.id_usuario if habilitada else None
    db.commit()
    db.refresh(huella)
    return huella

@router.post("/identificar")
def identificar_rostro(
    file: UploadFile = File(...),
    umbral: float = SIMILITUD_UMBRAL_DEFAULT,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user)
):
    contents = file.file.read()
    img_bgr = face_service.procesar_imagen_bytes(contents)
    if img_bgr is None:
        raise HTTPException(status_code=400, detail="Archivo de imagen inválido")

    embedding_query, _ = face_service.extraer_embedding(img_bgr)
    if embedding_query is None:
        raise HTTPException(status_code=400, detail="No se detectó ningún rostro en la captura")

    # Búsqueda 1:N sobre la caché en memoria de rostros habilitados
    mejor = face_service.buscar_mejor(embedding_query, db)
    if mejor is None:
        return {"coincidencia": False, "mensaje": "No hay rostros activos en la base de datos"}
    _, id_postulante_mejor, mejor_score = mejor

    if mejor_score >= umbral:
        postulante = db.query(Postulante).filter(
            Postulante.id_postulante == id_postulante_mejor
        ).first()
        if not postulante:
            return {"coincidencia": False, "mensaje": "Postulante no encontrado"}

        return {
            "coincidencia": True,
            "id_postulante": postulante.id_postulante,
            "ci": postulante.ci,
            "nombres": postulante.nombres,
            "apellidos": postulante.apellidos,
            "score": round(mejor_score, 4),
            "estado_biometria": postulante.estado_biometria
        }

    return {
        "coincidencia": False,
        "mejor_score": round(mejor_score, 4),
        "umbral_requerido": umbral,
        "mensaje": "No se encontró coincidencia sobre el umbral mínimo"
    }