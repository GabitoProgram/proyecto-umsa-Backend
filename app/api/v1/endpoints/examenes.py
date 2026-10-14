from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from sqlalchemy import distinct

from app.core.database import get_db
from app.api.deps import get_current_user, require_app_key, registrar_auditoria
from app.models.usuario import Usuario, RolUsuario
from app.models.academico import Examen
from app.models.asignacion import Asignacion, Inscripcion
from app.models.postulante import Postulante
from app.models.biometria import Huella, Rostro
from app.models.marcacion import RegistroIngreso, ResultadoMarcacion

router = APIRouter(prefix="/examenes", tags=["Examenes"])

class ToleranciaUpdate(BaseModel):
    tolerancia_minutos: int = Field(ge=0, le=180)


@router.get("/{id_examen}/postulantes")
def listar_postulantes_examen(
    id_examen: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user)
):
    examen = db.query(Examen).filter(Examen.id_examen == id_examen).first()
    if not examen:
        raise HTTPException(status_code=404, detail="Examen no encontrado")

    inscritos = db.query(Postulante, Inscripcion).join(
        Inscripcion, Inscripcion.id_postulante == Postulante.id_postulante
    ).filter(
        Inscripcion.id_gestion == examen.id_gestion,
        Inscripcion.id_carrera == examen.id_carrera
    ).all()
    resultado = []
    for postulante, inscripcion in inscritos:
        huellas = db.query(Huella).filter(
            Huella.id_postulante == postulante.id_postulante
        ).order_by(Huella.tipo_dedo).all()
        rostro = db.query(Rostro).filter(
            Rostro.id_postulante == postulante.id_postulante
        ).order_by(Rostro.fecha_registro.desc()).first()
        asignacion = db.query(Asignacion).filter(
            Asignacion.id_inscripcion == inscripcion.id_inscripcion,
            Asignacion.id_examen == id_examen
        ).first()
        resultado.append({
            "id_postulante": postulante.id_postulante,
            "id_inscripcion": inscripcion.id_inscripcion,
            "ci": postulante.ci,
            "nombre_completo": f"{postulante.nombres} {postulante.apellidos}",
            "estado_inscripcion": inscripcion.estado,
            "huellas": [
                {"id_huella": h.id_huella, "tipo_dedo": h.tipo_dedo, "habilitada": h.habilitada}
                for h in huellas
            ],
            "id_rostro": rostro.id_rostro if rostro else None,
            "rostro_habilitado": bool(rostro and rostro.habilitada),
            "numero_asiento": asignacion.asiento.numero_asiento if asignacion and asignacion.asiento else None,
            "nombre_aula": asignacion.aula.nombre if asignacion and asignacion.aula else None
        })
    return resultado

def verificar_es_admin(usuario: Usuario):
    roles_permitidos = [RolUsuario.SUPER_ADMIN, RolUsuario.ADMIN]
    if usuario.rol not in roles_permitidos:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operación permitida únicamente para administradores."
        )
    return usuario

@router.patch("/{id_examen}/tolerancia")
def actualizar_tolerancia(
    id_examen: int,
    payload: ToleranciaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    verificar_es_admin(current_user)
    
    examen = db.query(Examen).filter(Examen.id_examen == id_examen).first()
    if not examen:
        raise HTTPException(status_code=404, detail="Examen no encontrado")

    examen.tolerancia_minutos = payload.tolerancia_minutos
    db.commit()
    registrar_auditoria(
        db,
        current_user.id_usuario,
        "ACTUALIZAR_TOLERANCIA",
        "examenes",
        f"Examen {id_examen}: tolerancia={payload.tolerancia_minutos} minutos"
    )
    return {"id_examen": id_examen, "tolerancia_minutos": examen.tolerancia_minutos}

@router.get("/{id_examen}/contador")
def obtener_contador(
    id_examen: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_app_key)
):
    examen = db.query(Examen).filter(Examen.id_examen == id_examen).first()
    if not examen:
        raise HTTPException(status_code=404, detail="Examen no encontrado")

    # Total de postulantes con inscripción habilitada para la carrera/gestión del examen
    total_asignados = db.query(Inscripcion).filter(
        Inscripcion.id_gestion == examen.id_gestion,
        Inscripcion.id_carrera == examen.id_carrera,
        Inscripcion.estado == "HABILITADO"
    ).count()

    ingresados = db.query(distinct(RegistroIngreso.id_inscripcion)).filter(
        RegistroIngreso.id_examen == id_examen,
        RegistroIngreso.resultado == ResultadoMarcacion.ACEPTADO
    ).count()

    ultimos = db.query(RegistroIngreso).filter(
        RegistroIngreso.id_examen == id_examen
    ).order_by(RegistroIngreso.fecha_hora.desc()).limit(10).all()

    ultimos_data = [
        {
            "hora": r.fecha_hora.strftime("%H:%M:%S"),
            "metodo": r.metodo.value if hasattr(r.metodo, 'value') else str(r.metodo),
            "resultado": r.resultado.value if hasattr(r.resultado, 'value') else str(r.resultado),
            "estacion": r.estacion or "Estación"
        }
        for r in ultimos
    ]

    porcentaje = round((ingresados / total_asignados * 100), 1) if total_asignados > 0 else 0.0

    return {
        "id_examen": examen.id_examen,
        "materia": examen.materia,
        "total": total_asignados,
        "ingresados": ingresados,
        "total_asignados": total_asignados,
        "total_ingresados": ingresados,
        "total_pendientes": max(0, total_asignados - ingresados),
        "porcentaje": porcentaje,
        "porcentaje_asistencia": porcentaje,
        "ultimos_ingresos": ultimos_data
    }


@router.get("/activos-ahora")
def examenes_activos_ahora(
    db: Session = Depends(get_db),
    _: None = Depends(require_app_key)
):
    ahora = datetime.now()
    examenes = db.query(Examen).filter(Examen.fecha == ahora.date()).all()
    activos = []
    for examen in examenes:
        inicio = datetime.combine(examen.fecha, examen.hora_inicio)
        cierre = datetime.combine(examen.fecha, examen.hora_fin) + timedelta(
            minutes=examen.tolerancia_minutos or 0
        )
        if inicio <= ahora <= cierre:
            activos.append({
                "id_examen": examen.id_examen,
                "materia": examen.materia,
                "id_carrera": examen.id_carrera,
                "id_gestion": examen.id_gestion,
                "fecha": examen.fecha,
                "hora_inicio": examen.hora_inicio,
                "hora_fin": examen.hora_fin,
                "tolerancia_minutos": examen.tolerancia_minutos,
                "cierra_a_las": cierre.strftime("%H:%M")
            })
    return {"activos": activos}


@router.get("/activos-ahora/contadores")
def contadores_examenes_activos(
    db: Session = Depends(get_db),
    _: None = Depends(require_app_key)
):
    ahora = datetime.now()
    examenes = db.query(Examen).filter(Examen.fecha == ahora.date()).all()
    resultado = []
    for examen in examenes:
        inicio = datetime.combine(examen.fecha, examen.hora_inicio)
        cierre = datetime.combine(examen.fecha, examen.hora_fin) + timedelta(
            minutes=examen.tolerancia_minutos or 0
        )
        if not inicio <= ahora <= cierre:
            continue
        total = db.query(Inscripcion).filter(
            Inscripcion.id_gestion == examen.id_gestion,
            Inscripcion.id_carrera == examen.id_carrera,
            Inscripcion.estado == "HABILITADO"
        ).count()
        ingresados = db.query(distinct(RegistroIngreso.id_inscripcion)).filter(
            RegistroIngreso.id_examen == examen.id_examen,
            RegistroIngreso.resultado == ResultadoMarcacion.ACEPTADO
        ).count()
        resultado.append({
            "id_examen": examen.id_examen,
            "materia": examen.materia,
            "total_asignados": total,
            "total_ingresados": ingresados,
            "total_pendientes": max(0, total - ingresados),
            "porcentaje_asistencia": round(ingresados / total * 100, 2) if total else 0.0
        })
    return resultado
