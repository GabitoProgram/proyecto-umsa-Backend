import enum
from datetime import datetime, date, time
from sqlalchemy import Column, Integer, String, Date, Time, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.orm import relationship
from app.core.database import Base

class PeriodoGestion(str, enum.Enum):
    I = "I"
    II = "II"
    ANUAL = "ANUAL"

class Gestion(Base):
    __tablename__ = "gestiones"

    id_gestion = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False, unique=True)
    anio = Column(Integer, nullable=False)
    periodo = Column(
        PG_ENUM(PeriodoGestion, name="periodogestion", create_type=False),
        nullable=False,
        default=PeriodoGestion.I
    )
    fecha_inicio = Column(Date, nullable=True)
    fecha_fin = Column(Date, nullable=True)
    estado = Column(String(20), nullable=True)

    examenes = relationship("Examen", back_populates="gestion")
    inscripciones = relationship("Inscripcion", back_populates="gestion")


class Carrera(Base):
    __tablename__ = "carreras"

    id_carrera = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    codigo = Column(String(20), nullable=True)
    activa = Column(Boolean, default=True, nullable=False)

    examenes = relationship("Examen", back_populates="carrera")
    inscripciones = relationship("Inscripcion", back_populates="carrera")


class Examen(Base):
    __tablename__ = "examenes"

    id_examen = Column(Integer, primary_key=True, index=True)
    id_carrera = Column(Integer, ForeignKey("carreras.id_carrera"), nullable=False)
    id_gestion = Column(Integer, ForeignKey("gestiones.id_gestion"), nullable=False)
    materia = Column(String(150), nullable=False)
    fecha = Column(Date, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)
    estado = Column(String(20), default="PROGRAMADO")
    tolerancia_minutos = Column(Integer, default=10, nullable=False)

    carrera = relationship("Carrera", back_populates="examenes")
    gestion = relationship("Gestion", back_populates="examenes")
    asignaciones = relationship("Asignacion", back_populates="examen", cascade="all, delete-orphan")


class Inscripcion(Base):
    __tablename__ = "inscripciones"

    id_inscripcion = Column(Integer, primary_key=True, index=True)
    id_postulante = Column(Integer, ForeignKey("postulantes.id_postulante"), nullable=False)
    id_gestion = Column(Integer, ForeignKey("gestiones.id_gestion"), nullable=False)
    id_carrera = Column(Integer, ForeignKey("carreras.id_carrera"), nullable=False)
    codigo_postulante = Column(String(50), nullable=True)
    fecha_inscripcion = Column(DateTime, default=datetime.utcnow)
    estado = Column(String(20), default="HABILITADO")

    postulante = relationship("Postulante", back_populates="inscripciones")
    gestion = relationship("Gestion", back_populates="inscripciones")
    carrera = relationship("Carrera", back_populates="inscripciones")
    asignaciones = relationship("Asignacion", back_populates="inscripcion", cascade="all, delete-orphan")

# Alias para compatibilidad
InscripcionExamen = Inscripcion
