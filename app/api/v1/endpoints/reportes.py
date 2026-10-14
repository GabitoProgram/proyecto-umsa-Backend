import io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.usuario import Usuario
from app.models.academico import Examen
from app.models.asignacion import Asignacion, Inscripcion
from app.models.postulante import Postulante
from app.models.infraestructura import Aula, Asiento
from app.models.marcacion import RegistroIngreso, ResultadoMarcacion
from app.schemas.marcacion import ReporteAsistenciaOut, PostulanteReporteItem

router = APIRouter(prefix="/reportes", tags=["Reportes de Asistencia"])

@router.get("/examen/{id_examen}", response_model=ReporteAsistenciaOut)
def generar_reporte_asistencia_examen(
    id_examen: int,
    id_aula: Optional[int] = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user)
):
    examen = db.query(Examen).filter(Examen.id_examen == id_examen).first()
    if not examen:
        raise HTTPException(status_code=404, detail="Examen no encontrado")

    inscripciones = db.query(Inscripcion).filter(
        Inscripcion.id_gestion == examen.id_gestion,
        Inscripcion.id_carrera == examen.id_carrera,
        Inscripcion.estado == "HABILITADO"
    ).all()

    asistentes = []
    ausentes = []

    for inscripcion in inscripciones:
        postulante = db.query(Postulante).filter(Postulante.id_postulante == inscripcion.id_postulante).first()
        asignacion = db.query(Asignacion).filter(
            Asignacion.id_inscripcion == inscripcion.id_inscripcion,
            Asignacion.id_examen == id_examen
        ).first()
        if id_aula and (not asignacion or asignacion.id_aula != id_aula):
            continue
        aula = db.query(Aula).filter(Aula.id_aula == asignacion.id_aula).first() if asignacion else None
        asiento = db.query(Asiento).filter(Asiento.id_asiento == asignacion.id_asiento).first() if asignacion else None

        primer_ingreso = db.query(RegistroIngreso).filter(
            RegistroIngreso.id_examen == id_examen,
            RegistroIngreso.id_inscripcion == inscripcion.id_inscripcion,
            RegistroIngreso.resultado == ResultadoMarcacion.ACEPTADO
        ).order_by(RegistroIngreso.fecha_hora.asc()).first()

        item = PostulanteReporteItem(
            ci=postulante.ci,
            nombres=postulante.nombres,
            apellidos=postulante.apellidos,
            aula=aula.nombre if aula else "Sin asignar",
            numero_asiento=asiento.numero_asiento if asiento else 0,
            hora_ingreso=primer_ingreso.fecha_hora if primer_ingreso else None,
            metodo=primer_ingreso.metodo if primer_ingreso else None,
            score=primer_ingreso.score_similitud if primer_ingreso else None
        )

        if primer_ingreso:
            asistentes.append(item)
        else:
            ausentes.append(item)

    return ReporteAsistenciaOut(
        id_examen=examen.id_examen,
        materia=examen.materia,
        total_asistentes=len(asistentes),
        total_ausentes=len(ausentes),
        asistentes=asistentes,
        ausentes=ausentes
    )


@router.get("/examen/{id_examen}/excel")
def exportar_reporte_asistencia_excel(
    id_examen: int,
    id_aula: Optional[int] = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user)
):
    reporte = generar_reporte_asistencia_examen(id_examen, id_aula, db, _)
    filas = []
    for estado, personas in (("ASISTENTE", reporte.asistentes), ("AUSENTE", reporte.ausentes)):
        for persona in personas:
            filas.append({
                "Estado": estado,
                "CI": persona.ci,
                "Nombres": persona.nombres,
                "Apellidos": persona.apellidos,
                "Aula": persona.aula,
                "Asiento": persona.numero_asiento,
                "Hora ingreso": persona.hora_ingreso,
                "Método": persona.metodo.value if persona.metodo else "",
                "Score": persona.score
            })
    contenido = io.BytesIO()
    pd.DataFrame(filas).to_excel(contenido, index=False, engine="openpyxl")
    contenido.seek(0)
    return StreamingResponse(
        contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=reporte_examen_{id_examen}.xlsx"}
    )


@router.get("/examen/{id_examen}/pdf")
def exportar_reporte_asistencia_pdf(
    id_examen: int,
    id_aula: Optional[int] = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user)
):
    reporte = generar_reporte_asistencia_examen(id_examen, id_aula, db, _)
    contenido = io.BytesIO()
    documento = SimpleDocTemplate(
        contenido,
        pagesize=landscape(letter),
        rightMargin=0.35 * inch,
        leftMargin=0.35 * inch,
        topMargin=0.35 * inch,
        bottomMargin=0.35 * inch
    )
    estilos = getSampleStyleSheet()
    elementos = [
        Paragraph(f"Reporte de asistencia: {reporte.materia}", estilos["Title"]),
        Paragraph(
            f"Asistentes: {reporte.total_asistentes} | Ausentes: {reporte.total_ausentes}",
            estilos["Normal"]
        ),
        Spacer(1, 12)
    ]
    filas = [["Estado", "CI", "Nombres", "Apellidos", "Aula", "Asiento", "Hora", "Método"]]
    for estado, personas in (("ASISTENTE", reporte.asistentes), ("AUSENTE", reporte.ausentes)):
        for persona in personas:
            filas.append([
                estado,
                persona.ci,
                persona.nombres,
                persona.apellidos,
                persona.aula,
                str(persona.numero_asiento),
                str(persona.hora_ingreso or ""),
                persona.metodo.value if persona.metodo else ""
            ])
    tabla = Table(filas, repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F2C59")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(tabla)
    documento.build(elementos)
    contenido.seek(0)
    return StreamingResponse(
        contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=reporte_examen_{id_examen}.pdf"}
    )
