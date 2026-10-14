from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.academico import Inscripcion

class Asignacion(Base):
    __tablename__ = "asignaciones"

    id_asignacion = Column(Integer, primary_key=True, index=True)
    id_inscripcion = Column(Integer, ForeignKey("inscripciones.id_inscripcion"), nullable=False)
    id_examen = Column(Integer, ForeignKey("examenes.id_examen"), nullable=False)
    id_aula = Column(Integer, ForeignKey("aulas.id_aula"), nullable=False)
    id_asiento = Column(Integer, ForeignKey("asientos.id_asiento"), nullable=True)
    asignado_por = Column(Integer, ForeignKey("usuarios.id_usuario"), nullable=True)
    fecha_asignacion = Column(DateTime, default=datetime.utcnow)
    fecha_sorteo_asiento = Column(DateTime, nullable=True)

    inscripcion = relationship("Inscripcion", back_populates="asignaciones")
    examen = relationship("Examen", back_populates="asignaciones")
    aula = relationship("Aula")
    asiento = relationship("Asiento")
    registros_ingreso = relationship("RegistroIngreso", back_populates="asignacion")
