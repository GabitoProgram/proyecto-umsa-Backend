from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base

class Aula(Base):
    __tablename__ = "aulas"
    __table_args__ = (
        CheckConstraint('capacidad > 0', name='aulas_capacidad_check'),
    )

    id_aula = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), unique=True, nullable=False)
    ubicacion = Column(String(150), nullable=True)
    capacidad = Column(Integer, nullable=False)
    activa = Column(Boolean, default=True, nullable=False)

    asientos = relationship("Asiento", back_populates="aula", cascade="all, delete-orphan")
    asignaciones = relationship(
        "Asignacion",
        back_populates="aula",
        primaryjoin="Aula.id_aula == foreign(Asignacion.id_aula)"
    )

class Asiento(Base):
    __tablename__ = "asientos"
    __table_args__ = (
        CheckConstraint('numero_asiento > 0', name='asientos_numero_asiento_check'),
        UniqueConstraint('id_aula', 'numero_asiento', name='uq_aula_numero_asiento'),
        UniqueConstraint('id_aula', 'id_asiento', name='uq_aula_asiento_compuesto'),
    )

    id_asiento = Column(Integer, primary_key=True, index=True)
    id_aula = Column(Integer, ForeignKey("aulas.id_aula", ondelete="CASCADE"), nullable=False)
    numero_asiento = Column(Integer, nullable=False)
    fila = Column(String(10), nullable=True)
    columna = Column(Integer, nullable=True)
    habilitado = Column(Boolean, default=True, nullable=False)

    aula = relationship("Aula", back_populates="asientos")
    asignaciones = relationship(
        "Asignacion",
        back_populates="asiento",
        primaryjoin="Asiento.id_asiento == foreign(Asignacion.id_asiento)"
    )
