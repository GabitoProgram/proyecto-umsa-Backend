from datetime import datetime, date, time
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from app.models.marcacion import MetodoMarcacion, ResultadoMarcacion

class MarcacionRespuestaOut(BaseModel):
    resultado: ResultadoMarcacion
    metodo: MetodoMarcacion
    mensaje: str
    id_postulante: Optional[int] = None
    ci: Optional[str] = None
    nombre_completo: Optional[str] = None
    aula: Optional[str] = None
    numero_asiento: Optional[int] = None
    score_similitud: Optional[float] = None
    fecha_hora: datetime

class ContadorTiempoRealOut(BaseModel):
    id_examen: int
    materia: str
    carrera: str
    fecha: date
    hora_inicio: time
    hora_fin: time
    total_asignados: int
    total_ingresados: int
    total_pendientes: int
    porcentaje_asistencia: float

class PostulanteReporteItem(BaseModel):
    ci: str
    nombres: str
    apellidos: str
    aula: str
    numero_asiento: int
    hora_ingreso: Optional[datetime] = None
    metodo: Optional[MetodoMarcacion] = None
    score: Optional[float] = None

class ReporteAsistenciaOut(BaseModel):
    id_examen: int
    materia: str
    total_asistentes: int
    total_ausentes: int
    asistentes: List[PostulanteReporteItem]
    ausentes: List[PostulanteReporteItem]
