from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class AsignacionAulaIn(BaseModel):
    id_inscripcion: int
    id_examen: int
    id_aula: int

class AsignacionOut(BaseModel):
    id_asignacion: int
    id_inscripcion: int
    id_examen: int
    id_aula: int
    id_asiento: int
    numero_asiento: int
    nombre_aula: str
    fecha_asignacion: datetime
    fecha_sorteo_asiento: datetime
    model_config = ConfigDict(from_attributes=True)
