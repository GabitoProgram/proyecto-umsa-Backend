import secrets
from typing import Optional
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.usuario import Usuario, RolUsuario

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False)

def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Usuario:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token no proporcionado")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="No se pudo validar credenciales")

    try:
        usuario_id = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido")

    usuario = db.query(Usuario).filter(Usuario.id_usuario == usuario_id).first()
    if not usuario or not usuario.activo:
        raise HTTPException(status_code=401, detail="Usuario inactivo o no existe")
    return usuario


def get_current_superadmin(user: Usuario = Depends(get_current_user)) -> Usuario:
    if user.rol != RolUsuario.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Permiso denegado: Se requiere rol SUPER_ADMIN")
    return user

def require_app_key(
    x_app_key: Optional[str] = Header(None, alias="X-App-Key")
) -> None:
    if not x_app_key or not secrets.compare_digest(x_app_key, settings.APP_CLIENT_KEY):
        raise HTTPException(status_code=401, detail="Clave de aplicación inválida o ausente")

def registrar_auditoria(db: Session, id_usuario: Optional[int], accion: str, tabla: str, detalle: str):
    from app.models.auditoria import Auditoria
    registro = Auditoria(
        id_usuario=id_usuario,
        accion=accion,
        entidad_afectada=tabla,
        detalle=detalle
    )
    db.add(registro)
    db.commit()
# Alias para compatibilidad con endpoints existentes
require_super_admin = get_current_superadmin

