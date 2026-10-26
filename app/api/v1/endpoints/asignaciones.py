import random
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user, registrar_auditoria
from app.models.usuario import Usuario
from app.models.asignacion import Asignacion, Inscripcion
from app.models.academico import Examen
from app.models.infraestructura import Aula, Asiento
from app.models.marcacion import RegistroIngreso
from app.schemas.asignacion import AsignacionAulaIn, AsignacionOut

router = APIRouter(prefix="/asignaciones", tags=["Asignaciones y Sorteo de Asientos"])


class SorteoExamenIn(BaseModel):
    id_examen: int
    id_aula: Optional[int] = None           # compatibilidad: una sola aula
    id_aulas: Optional[List[int]] = None    # una o varias aulas

    def lista_aulas(self) -> List[int]:
        if self.id_aulas:
            return list(dict.fromkeys(self.id_aulas))
        if self.id_aula is not None:
            return [self.id_aula]
        return []


class DisponibilidadOut(BaseModel):
    id_examen: int
    total_postulantes: int       # inscritos habilitados de la carrera/gestión
    ya_asignados: int            # con asiento ya asignado
    pendientes: int              # faltan por asignar
    asientos_libres: int         # libres en las aulas seleccionadas
    diferencia: int              # positivos = sillas de sobra, negativos = faltan
    suficiente: bool


class EditarAsignacionIn(BaseModel):
    id_aula: int
    id_asiento: int


@router.patch("/{id_asignacion}", response_model=AsignacionOut)
def editar_asignacion(
    id_asignacion: int,
    payload: EditarAsignacionIn,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user),
):
    asignacion = db.query(Asignacion).filter(
        Asignacion.id_asignacion == id_asignacion
    ).first()
    if not asignacion:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")

    aula = db.query(Aula).filter(
        Aula.id_aula == payload.id_aula,
        Aula.activa.is_(True),
    ).first()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada o inactiva")

    asiento = db.query(Asiento).filter(
        Asiento.id_asiento == payload.id_asiento,
        Asiento.id_aula == payload.id_aula,
        Asiento.habilitado.is_(True),
    ).first()
    if not asiento:
        raise HTTPException(
            status_code=400,
            detail="El asiento no existe, está deshabilitado o no pertenece al aula",
        )

    ocupado = db.query(Asignacion).filter(
        Asignacion.id_examen == asignacion.id_examen,
        Asignacion.id_asiento == payload.id_asiento,
        Asignacion.id_asignacion != id_asignacion,
    ).first()
    if ocupado:
        raise HTTPException(
            status_code=409,
            detail="Ese asiento ya está asignado a otro postulante en este examen",
        )

    asignacion.id_aula = payload.id_aula
    asignacion.id_asiento = payload.id_asiento
    db.commit()
    db.refresh(asignacion)
    registrar_auditoria(
        db,
        admin.id_usuario,
        "EDITAR_ASIGNACION",
        "asignaciones",
        f"Asignación {id_asignacion}: aula {aula.nombre}, asiento #{asiento.numero_asiento}",
    )
    return AsignacionOut(
        id_asignacion=asignacion.id_asignacion,
        id_inscripcion=asignacion.id_inscripcion,
        id_examen=asignacion.id_examen,
        id_aula=asignacion.id_aula,
        id_asiento=asignacion.id_asiento,
        numero_asiento=asiento.numero_asiento,
        nombre_aula=aula.nombre,
        fecha_asignacion=asignacion.fecha_asignacion,
        fecha_sorteo_asiento=asignacion.fecha_sorteo_asiento,
    )


def _pendientes_examen(db: Session, examen: Examen) -> List[Inscripcion]:
    inscripciones_asignadas = db.query(Asignacion.id_inscripcion).filter(
        Asignacion.id_examen == examen.id_examen
    ).subquery()
    return db.query(Inscripcion).filter(
        Inscripcion.id_gestion == examen.id_gestion,
        Inscripcion.id_carrera == examen.id_carrera,
        Inscripcion.estado == "HABILITADO",
        ~Inscripcion.id_inscripcion.in_(inscripciones_asignadas)
    ).all()


def _asientos_libres_aulas(db: Session, examen: Examen, ids_aulas: List[int]) -> List[Asiento]:
    if not ids_aulas:
        return []
    ocupados = db.query(Asignacion.id_asiento).filter(
        Asignacion.id_examen == examen.id_examen,
        Asignacion.id_aula.in_(ids_aulas)
    ).subquery()
    return db.query(Asiento).filter(
        Asiento.id_aula.in_(ids_aulas),
        Asiento.habilitado.is_(True),
        ~Asiento.id_asiento.in_(ocupados)
    ).all()


@router.get("/examen/{id_examen}/disponibilidad", response_model=DisponibilidadOut)
def disponibilidad_examen(
    id_examen: int,
    id_aulas: Optional[List[int]] = Query(None),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user)
):
    examen = db.query(Examen).filter(Examen.id_examen == id_examen).first()
    if not examen:
        raise HTTPException(status_code=404, detail="Examen no encontrado")

    total = db.query(Inscripcion).filter(
        Inscripcion.id_gestion == examen.id_gestion,
        Inscripcion.id_carrera == examen.id_carrera,
        Inscripcion.estado == "HABILITADO"
    ).count()
    pendientes = len(_pendientes_examen(db, examen))
    ya_asignados = total - pendientes
    libres = len(_asientos_libres_aulas(db, examen, id_aulas or []))
    diferencia = libres - pendientes
    return DisponibilidadOut(
        id_examen=id_examen,
        total_postulantes=total,
        ya_asignados=ya_asignados,
        pendientes=pendientes,
        asientos_libres=libres,
        diferencia=diferencia,
        suficiente=libres >= pendientes,
    )

@router.post("/sortear-asiento", response_model=AsignacionOut)
def asignar_aula_y_sortear_asiento(
    payload: AsignacionAulaIn,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user)
):
    # 1. Validar que la inscripción exista
    inscripcion = db.query(Inscripcion).filter(Inscripcion.id_inscripcion == payload.id_inscripcion).first()
    if not inscripcion:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada")

    # 2. Validar que el examen exista
    examen = db.query(Examen).filter(Examen.id_examen == payload.id_examen).first()
    if not examen:
        raise HTTPException(status_code=404, detail="Examen no encontrado")

    # 3. Validar coherencia: El examen debe corresponder a la carrera de la inscripción
    if examen.id_carrera != inscripcion.id_carrera:
        raise HTTPException(
            status_code=400,
            detail="Inconsistencia académica: El examen no corresponde a la carrera inscrita por el postulante"
        )

    if examen.id_gestion != inscripcion.id_gestion:
        raise HTTPException(
            status_code=400,
            detail="Inconsistencia académica: El examen no corresponde a la gestión de la inscripción"
        )

    if inscripcion.estado != "HABILITADO":
        raise HTTPException(
            status_code=409,
            detail="Solo se pueden asignar asientos a inscripciones habilitadas"
        )

    # 4. Validar que el postulante no tenga ya una asignación para este examen
    asignacion_previa = db.query(Asignacion).filter(
        Asignacion.id_inscripcion == payload.id_inscripcion,
        Asignacion.id_examen == payload.id_examen
    ).first()
    if asignacion_previa:
        raise HTTPException(status_code=400, detail="El postulante ya tiene aula y asiento asignados para este examen")

    # 5. Validar existencia y estado del aula
    aula = db.query(Aula).filter(Aula.id_aula == payload.id_aula, Aula.activa == True).first()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada o inactiva")

    # 6. Obtener asientos del aula que ya están ocupados para este examen específico
    asientos_ocupados_ids = db.query(Asignacion.id_asiento).filter(
        Asignacion.id_examen == payload.id_examen,
        Asignacion.id_aula == payload.id_aula
    ).subquery()

    # 7. Buscar asientos habilitados libres en esa aula
    asientos_libres = db.query(Asiento).filter(
        Asiento.id_aula == payload.id_aula,
        Asiento.habilitado == True,
        ~Asiento.id_asiento.in_(asientos_ocupados_ids)
    ).all()

    if not asientos_libres:
        raise HTTPException(
            status_code=400,
            detail=f"El aula '{aula.nombre}' no tiene asientos libres disponibles para este examen (Capacidad agotada)"
        )

    # 8. Sorteo automático aleatorio entre los asientos disponibles
    asiento_sorteado = random.choice(asientos_libres)

    # 9. Guardar asignación
    nueva_asignacion = Asignacion(
        id_inscripcion=payload.id_inscripcion,
        id_examen=payload.id_examen,
        id_aula=payload.id_aula,
        id_asiento=asiento_sorteado.id_asiento,
        asignado_por=admin.id_usuario
    )
    db.add(nueva_asignacion)
    db.commit()
    db.refresh(nueva_asignacion)

    registrar_auditoria(
        db, admin.id_usuario, "ASIGNACION_AULA_ASIENTO", "asignaciones",
        f"Inscripción {payload.id_inscripcion} asignada a Aula {aula.nombre}, Asiento #{asiento_sorteado.numero_asiento}"
    )

    return AsignacionOut(
        id_asignacion=nueva_asignacion.id_asignacion,
        id_inscripcion=nueva_asignacion.id_inscripcion,
        id_examen=nueva_asignacion.id_examen,
        id_aula=nueva_asignacion.id_aula,
        id_asiento=nueva_asignacion.id_asiento,
        numero_asiento=asiento_sorteado.numero_asiento,
        nombre_aula=aula.nombre,
        fecha_asignacion=nueva_asignacion.fecha_asignacion,
        fecha_sorteo_asiento=nueva_asignacion.fecha_sorteo_asiento
    )


@router.post("/sortear-examen", response_model=List[AsignacionOut])
def sortear_asientos_examen(
    payload: SorteoExamenIn,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user)
):
    examen = db.query(Examen).filter(Examen.id_examen == payload.id_examen).first()
    if not examen:
        raise HTTPException(status_code=404, detail="Examen no encontrado")

    ids_aulas = payload.lista_aulas()
    if not ids_aulas:
        raise HTTPException(status_code=422, detail="Debe indicar al menos un aula")

    aulas = db.query(Aula).filter(
        Aula.id_aula.in_(ids_aulas),
        Aula.activa.is_(True)
    ).all()
    if len(aulas) != len(ids_aulas):
        raise HTTPException(status_code=404, detail="Una o más aulas no existen o están inactivas")

    pendientes = _pendientes_examen(db, examen)
    asientos_libres = _asientos_libres_aulas(db, examen, ids_aulas)

    if not asientos_libres and pendientes:
        raise HTTPException(
            status_code=409,
            detail="Las aulas seleccionadas no tienen asientos libres habilitados."
        )
    # Nota: si faltan sillas no se bloquea; se asignan las disponibles y el resto queda pendiente.

    random.shuffle(asientos_libres)
    nombres_aula = {aula.id_aula: aula.nombre for aula in aulas}
    ahora = datetime.utcnow()
    nuevas = []
    for inscripcion, asiento in zip(pendientes, asientos_libres):
        asignacion = Asignacion(
            id_inscripcion=inscripcion.id_inscripcion,
            id_examen=payload.id_examen,
            id_aula=asiento.id_aula,
            id_asiento=asiento.id_asiento,
            asignado_por=admin.id_usuario,
            fecha_asignacion=ahora,
            fecha_sorteo_asiento=ahora
        )
        asignacion._numero_asiento = asiento.numero_asiento
        asignacion._nombre_aula = nombres_aula.get(asiento.id_aula, "Aula")
        nuevas.append(asignacion)

    db.add_all(nuevas)
    db.commit()

    registrar_auditoria(
        db,
        admin.id_usuario,
        "SORTEO_MASIVO_ASIENTOS",
        "asignaciones",
        (
            f"Examen {payload.id_examen}: {len(nuevas)} asignaciones en "
            f"{len(aulas)} aula(s). Pendientes sin silla: {max(0, len(pendientes) - len(asientos_libres))}"
        )
    )

    return [AsignacionOut(
        id_asignacion=asignacion.id_asignacion,
        id_inscripcion=asignacion.id_inscripcion,
        id_examen=asignacion.id_examen,
        id_aula=asignacion.id_aula,
        id_asiento=asignacion.id_asiento,
        numero_asiento=asignacion._numero_asiento,
        nombre_aula=asignacion._nombre_aula,
        fecha_asignacion=asignacion.fecha_asignacion,
        fecha_sorteo_asiento=asignacion.fecha_sorteo_asiento
    ) for asignacion in nuevas]


@router.delete("/examen/{id_examen}")
def limpiar_asignaciones_examen(
    id_examen: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user)
):
    """Elimina las asignaciones (y sus registros de ingreso) de un examen para volver a sortear."""
    examen = db.query(Examen).filter(Examen.id_examen == id_examen).first()
    if not examen:
        raise HTTPException(status_code=404, detail="Examen no encontrado")

    asignaciones = db.query(Asignacion).filter(Asignacion.id_examen == id_examen).all()
    ids = [a.id_asignacion for a in asignaciones]
    if ids:
        db.query(RegistroIngreso).filter(RegistroIngreso.id_asignacion.in_(ids)).delete(
            synchronize_session=False
        )
    for asignacion in asignaciones:
        db.delete(asignacion)
    db.commit()
    registrar_auditoria(
        db, admin.id_usuario, "LIMPIAR_ASIGNACIONES", "asignaciones",
        f"Examen {id_examen}: {len(ids)} asignaciones eliminadas"
    )
    return {"mensaje": f"Se eliminaron {len(ids)} asignaciones del examen."}


@router.get("/examen/{id_examen}", response_model=List[AsignacionOut])
def listar_asignaciones_examen(
    id_examen: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user)
):
    asignaciones = db.query(Asignacion).filter(Asignacion.id_examen == id_examen).all()
    resultado = []
    for a in asignaciones:
        asiento = db.query(Asiento).filter(Asiento.id_asiento == a.id_asiento).first()
        aula = db.query(Aula).filter(Aula.id_aula == a.id_aula).first()
        resultado.append(
            AsignacionOut(
                id_asignacion=a.id_asignacion,
                id_inscripcion=a.id_inscripcion,
                id_examen=a.id_examen,
                id_aula=a.id_aula,
                id_asiento=a.id_asiento,
                numero_asiento=asiento.numero_asiento if asiento else 0,
                nombre_aula=aula.nombre if aula else "N/A",
                fecha_asignacion=a.fecha_asignacion,
                fecha_sorteo_asiento=a.fecha_sorteo_asiento
            )
        )
    return resultado
