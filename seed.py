from app.core.database import SessionLocal
from app.models.usuario import Usuario, RolUsuario
from app.core.security import get_password_hash

def seed_super_admin():
    db = SessionLocal()
    try:
        user = db.query(Usuario).filter(Usuario.usuario == "admin").first()
        if not user:
            super_admin = Usuario(
                nombre_completo="Administrador General UMSA",
                genero="M",
                usuario="admin",
                password_hash=get_password_hash("Admin123*"),
                rol=RolUsuario.SUPER_ADMIN,
                activo=True
            )
            db.add(super_admin)
            db.commit()
            print("Usuario 'admin' creado exitosamente con clave: Admin123*")
        else:
            print("El usuario 'admin' ya existe en la base de datos.")
    finally:
        db.close()

if __name__ == "__main__":
    seed_super_admin()