from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, registrar_auditoria
from app.core.database import get_db
from app.models.academico import Carrera, Gestion, Inscripcion
from app.models.postulante import Postulante
from app.models.usuario import Usuario

router = APIRouter(prefix="/inscripciones", tags=["Inscripciones"])

EstadoInscripcion = Literal["HABILITADO", "INHABILITADO", "RETIRADO"]


class InscripcionCreate(BaseModel):
    id_postulante: int
    id_gestion: int
    id_carrera: int
    codigo_postulante: Optional[str] = Field(default=None, max_length=50)
    estado: EstadoInscripcion = "HABILITADO"


class InscripcionUpdate(BaseModel):
    estado: EstadoInscripcion


class InscripcionOut(BaseModel):
    id_inscripcion: int
    id_postulante: int
    id_gestion: int
    id_carrera: int
    codigo_postulante: Optional[str]
    estado: str

    model_config = ConfigDict(from_attributes=True)


class PostulanteGestionOut(BaseModel):
    id_postulante: int
    ci: str
    nombre_completo: str
    carreras: list[dict]


@router.get("/gestion/{id_gestion}/postulantes", response_model=List[PostulanteGestionOut])
def listar_postulantes_gestion(
    id_gestion: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user)
):
    filas = db.query(Inscripcion, Postulante, Carrera).join(
        Postulante, Postulante.id_postulante == Inscripcion.id_postulante
    ).join(
        Carrera, Carrera.id_carrera == Inscripcion.id_carrera
    ).filter(Inscripcion.id_gestion == id_gestion).order_by(
        Postulante.apellidos, Postulante.nombres
    ).all()
    agrupados = {}
    for inscripcion, postulante, carrera in filas:
        item = agrupados.setdefault(postulante.id_postulante, {
            "id_postulante": postulante.id_postulante,
            "ci": postulante.ci,
            "nombre_completo": f"{postulante.nombres} {postulante.apellidos}",
            "carreras": []
        })
        item["carreras"].append({
            "id_carrera": carrera.id_carrera,
            "nombre": carrera.nombre,
            "estado": inscripcion.estado
        })
    return list(agrupados.values())


@router.get("", response_model=List[InscripcionOut])
def listar_inscripciones(
    id_gestion: Optional[int] = None,
    id_carrera: Optional[int] = None,
    estado: Optional[EstadoInscripcion] = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user)
):
    query = db.query(Inscripcion)
    if id_gestion is not None:
        query = query.filter(Inscripcion.id_gestion == id_gestion)
    if id_carrera is not None:
        query = query.filter(Inscripcion.id_carrera == id_carrera)
    if estado is not None:
        query = query.filter(Inscripcion.estado == estado)
    return query.order_by(Inscripcion.fecha_inscripcion.desc()).all()


@router.post("", response_model=InscripcionOut, status_code=status.HTTP_201_CREATED)
def crear_inscripcion(
    payload: InscripcionCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user)
):
    postulante = db.query(Postulante).filter(Postulante.id_postulante == payload.id_postulante).first()
    if not postulante:
        raise HTTPException(status_code=404, detail="Postulante no encontrado")
    gestion = db.query(Gestion).filter(Gestion.id_gestion == payload.id_gestion).first()
    if not gestion:
        raise HTTPException(status_code=404, detail="Gestión no encontrada")
    carrera = db.query(Carrera).filter(Carrera.id_carrera == payload.id_carrera).first()
    if not carrera:
        raise HTTPException(status_code=404, detail="Carrera no encontrada")
    if not carrera.activa:
        raise HTTPException(status_code=409, detail="La carrera está inactiva")

    duplicate = db.query(Inscripcion).filter(
        Inscripcion.id_postulante == payload.id_postulante,
        Inscripcion.id_gestion == payload.id_gestion,
        Inscripcion.id_carrera == payload.id_carrera
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="El postulante ya está inscrito en esa carrera y gestión")

    total_carreras = db.query(Inscripcion).filter(
        Inscripcion.id_postulante == payload.id_postulante,
        Inscripcion.id_gestion == payload.id_gestion,
        Inscripcion.estado != "RETIRADO"
    ).count()
    if total_carreras >= 2:
        raise HTTPException(
            status_code=409,
            detail="El postulante no puede inscribirse en más de 2 carreras por gestión"
        )

    inscripcion = Inscripcion(**payload.model_dump())
    db.add(inscripcion)
    db.commit()
    db.refresh(inscripcion)
    registrar_auditoria(
        db,
        admin.id_usuario,
        "CREAR_INSCRIPCION",
        "inscripciones",
        f"Postulante {payload.id_postulante}, gestión {payload.id_gestion}, carrera {payload.id_carrera}"
    )
    return inscripcion


@router.get("/postulante/{id_postulante}", response_model=List[InscripcionOut])
def listar_inscripciones(
    id_postulante: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user)
):
    return db.query(Inscripcion).filter(
        Inscripcion.id_postulante == id_postulante
    ).order_by(Inscripcion.fecha_inscripcion.desc()).all()


@router.patch("/{id_inscripcion}", response_model=InscripcionOut)
def actualizar_inscripcion(
    id_inscripcion: int,
    payload: InscripcionUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user)
):
    inscripcion = db.query(Inscripcion).filter(Inscripcion.id_inscripcion == id_inscripcion).first()
    if not inscripcion:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada")
    inscripcion.estado = payload.estado
    db.commit()
    db.refresh(inscripcion)
    registrar_auditoria(db, admin.id_usuario, "ACTUALIZAR_INSCRIPCION", "inscripciones", f"ID {id_inscripcion}")
    return inscripcion
