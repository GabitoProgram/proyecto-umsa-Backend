from sqlalchemy.dialects.postgresql import ENUM

from app.core.database import Base, engine
import app.models


ENUMS = {
    "rol_usuario_enum": ("SUPER_ADMIN", "ADMIN"),
    "periodogestion": ("I", "II", "ANUAL"),
    "estado_biometria_enum": ("PENDIENTE", "COMPLETO", "INCOMPLETO"),
    "origen_registro_enum": ("MANUAL", "EXCEL"),
    "metodomarcacion": ("ROSTRO", "HUELLA", "MANUAL"),
    "resultadomarcacion": ("ACEPTADO", "RECHAZADO"),
}


def initialize_database() -> None:
    with engine.begin() as connection:
        for name, values in ENUMS.items():
            ENUM(*values, name=name).create(connection, checkfirst=True)
    Base.metadata.create_all(bind=engine)
    print("Esquema de base de datos creado o actualizado.")


if __name__ == "__main__":
    initialize_database()
