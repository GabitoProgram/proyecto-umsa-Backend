from datetime import datetime
from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, LargeBinary, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import ARRAY, REAL
from sqlalchemy.orm import relationship
from app.core.database import Base

class Huella(Base):
    __tablename__ = "huellas"
    __table_args__ = (
        CheckConstraint('tipo_dedo BETWEEN 1 AND 10', name='huellas_tipo_dedo_check'),
        UniqueConstraint('id_postulante', 'tipo_dedo', name='uq_postulante_dedo'),
    )

    id_huella = Column(Integer, primary_key=True, index=True)
    id_postulante = Column(Integer, ForeignKey("postulantes.id_postulante", ondelete="CASCADE"), nullable=False)
    tipo_dedo = Column(Integer, nullable=False)
    plantilla_biometrica = Column(LargeBinary, nullable=False)
    habilitada = Column(Boolean, default=False, nullable=False)
    habilitada_por = Column(Integer, ForeignKey("usuarios.id_usuario", ondelete="SET NULL"), nullable=True)
    fecha_registro = Column(DateTime, default=datetime.utcnow, nullable=False)

    postulante = relationship("Postulante", back_populates="huellas")

class Rostro(Base):
    __tablename__ = "rostros"

    id_rostro = Column(Integer, primary_key=True, index=True)
    id_postulante = Column(Integer, ForeignKey("postulantes.id_postulante", ondelete="CASCADE"), nullable=False)
    embedding = Column(ARRAY(REAL, dimensions=1), nullable=False)
    imagen_captura = Column(LargeBinary, nullable=True)
    habilitada = Column(Boolean, default=False, nullable=False)
    habilitada_por = Column(Integer, ForeignKey("usuarios.id_usuario", ondelete="SET NULL"), nullable=True)
    fecha_registro = Column(DateTime, default=datetime.utcnow, nullable=False)

    postulante = relationship("Postulante", back_populates="rostros")
# Alias de compatibilidad
BiometriaFacial = Rostro
BiometriaDactilar = Huella
