import os
import secrets

from app.core.database import SessionLocal
from app.models.usuario import Usuario, RolUsuario
from app.core.security import get_password_hash


def seed_super_admin():
    """Crea el superadministrador inicial si no existe.

    La contraseña sale de la variable de entorno ``ADMIN_INITIAL_PASSWORD``;
    si no está definida se genera una aleatoria y se muestra UNA sola vez.
    Cámbiala apenas entres al sistema.
    """
    db = SessionLocal()
    try:
        user = db.query(Usuario).filter(Usuario.usuario == "admin").first()
        if not user:
            password = os.getenv("ADMIN_INITIAL_PASSWORD") or secrets.token_urlsafe(12)
            super_admin = Usuario(
                nombre_completo="Administrador General UMSA",
                genero="M",
                usuario="admin",
                password_hash=get_password_hash(password),
                rol=RolUsuario.SUPER_ADMIN,
                activo=True
            )
            db.add(super_admin)
            db.commit()
            print("Usuario 'admin' creado exitosamente.")
            if not os.getenv("ADMIN_INITIAL_PASSWORD"):
                print(f"Contraseña inicial (anótala, no se vuelve a mostrar): {password}")
        else:
            print("El usuario 'admin' ya existe en la base de datos.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_super_admin()