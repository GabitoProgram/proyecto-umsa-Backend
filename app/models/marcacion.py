import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.orm import relationship
from app.core.database import Base

class MetodoMarcacion(str, enum.Enum):
    ROSTRO = "ROSTRO"
    HUELLA = "HUELLA"
    MANUAL = "MANUAL"

class ResultadoMarcacion(str, enum.Enum):
    ACEPTADO = "ACEPTADO"
    RECHAZADO = "RECHAZADO"

class RegistroIngreso(Base):
    __tablename__ = "registros_ingreso"

    id_registro = Column(Integer, primary_key=True, index=True)
    id_asignacion = Column(Integer, ForeignKey("asignaciones.id_asignacion"), nullable=True)
    id_examen = Column(Integer, ForeignKey("examenes.id_examen"), nullable=True)
    id_inscripcion = Column(Integer, ForeignKey("inscripciones.id_inscripcion"), nullable=True)
    metodo = Column(
        PG_ENUM(MetodoMarcacion, name="metodomarcacion", create_type=False),
        nullable=False,
        default=MetodoMarcacion.ROSTRO
    )
    resultado = Column(
        PG_ENUM(ResultadoMarcacion, name="resultadomarcacion", create_type=False),
        nullable=False,
        default=ResultadoMarcacion.ACEPTADO
    )
    score_similitud = Column(Float, nullable=True)
    fecha_hora = Column(DateTime, default=datetime.utcnow, nullable=False)
    estacion = Column(String(100), nullable=True)
    observacion = Column(String(255), nullable=True)

    asignacion = relationship("Asignacion", back_populates="registros_ingreso")

# Alias para compatibilidad con código existente
Marcacion = RegistroIngreso
