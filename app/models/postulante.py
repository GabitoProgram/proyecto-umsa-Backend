import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.orm import relationship
from app.core.database import Base

class EstadoBiometria(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    COMPLETO = "COMPLETO"
    INCOMPLETO = "INCOMPLETO"

class OrigenRegistro(str, enum.Enum):
    MANUAL = "MANUAL"
    EXCEL = "EXCEL"

class Postulante(Base):
    __tablename__ = "postulantes"

    id_postulante = Column(Integer, primary_key=True, index=True)
    ci = Column(String, unique=True, index=True, nullable=False)
    nombres = Column(String, nullable=False)
    apellidos = Column(String, nullable=False)
    genero = Column(String, nullable=True)
    fecha_nacimiento = Column(Date, nullable=True)
    telefono = Column(String, nullable=True)
    correo = Column(String, nullable=True)
    direccion = Column(String, nullable=True)
    
    estado_biometria = Column(
        PG_ENUM(EstadoBiometria, name="estado_biometria_enum", create_type=False),
        default=EstadoBiometria.PENDIENTE,
        nullable=True
    )
    origen_registro = Column(
        PG_ENUM(OrigenRegistro, name="origen_registro_enum", create_type=False),
        default=OrigenRegistro.MANUAL,
        nullable=True
    )
    fecha_registro = Column(DateTime, default=datetime.utcnow)

    # Relaciones que coinciden exactamente con tus tablas
    rostros = relationship("Rostro", back_populates="postulante", cascade="all, delete-orphan")
    huellas = relationship("Huella", back_populates="postulante", cascade="all, delete-orphan")
    inscripciones = relationship("Inscripcion", back_populates="postulante", cascade="all, delete-orphan")
