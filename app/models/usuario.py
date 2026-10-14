import enum
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.orm import relationship
from app.core.database import Base

class RolUsuario(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"

class Usuario(Base):
    __tablename__ = "usuarios"

    id_usuario = Column(Integer, primary_key=True, index=True)
    nombre_completo = Column(String(150), nullable=False)
    genero = Column(String(20), nullable=True)
    usuario = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    rol = Column(
        PG_ENUM(RolUsuario, name="rol_usuario_enum", create_type=False),
        default=RolUsuario.ADMIN,
        nullable=False
    )
    activo = Column(Boolean, default=True, nullable=False)

    auditorias = relationship("Auditoria", back_populates="usuario")


