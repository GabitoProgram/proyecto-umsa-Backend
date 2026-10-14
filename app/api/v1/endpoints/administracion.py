from datetime import date, time
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user, require_super_admin, registrar_auditoria
from app.models.usuario import Usuario, RolUsuario
from app.models.auditoria import Auditoria
from app.models.academico import Carrera, Gestion, Examen, PeriodoGestion
from app.models.infraestructura import Aula, Asiento
from app.schemas.base import (
    CarreraCreate, CarreraOut,
    GestionCreate, GestionOut,
    AulaCreate, AulaOut, AsientoOut,
    ExamenCreate,
    UsuarioCreate, UsuarioOut
)
from app.core.security import get_password_hash


class UsuarioUpdate(BaseModel):
    nombre_completo: str | None = None
    genero: str | None = None
    rol: RolUsuario | None = None
    activo: bool | None = None
    password: str | None = None


class AulaUpdate(BaseModel):
    nombre: str | None = None
    ubicacion: str | None = None
    capacidad: int | None = None
    activa: bool | None = None


class AsientoUpdate(BaseModel):
    numero_asiento: int | None = None
    fila: str | None = None
    columna: int | None = None
    habilitado: bool | None = None


class AsientosCreate(BaseModel):
    cantidad: int = Field(ge=1, le=1000)
    numero_inicial: int = Field(default=1, ge=1)


class CarreraUpdate(BaseModel):
    nombre: str | None = None
    codigo: str | None = None
    activa: bool | None = None


class GestionUpdate(BaseModel):
    nombre: str | None = None
    anio: int | None = None
    periodo: PeriodoGestion | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    estado: str | None = None


class ExamenUpdate(BaseModel):
    id_carrera: int | None = None
    id_gestion: int | None = None
    materia: str | None = None
    fecha: date | None = None
    hora_inicio: time | None = None
    hora_fin: time | None = None
    estado: str | None = None
    tolerancia_minutos: int | None = Field(default=None, ge=0, le=180)


class ExamenOut(BaseModel):
    id_examen: int
    id_carrera: int
    id_gestion: int
    materia: str
    fecha: date
    hora_inicio: time
    hora_fin: time
    estado: str
    tolerancia_minutos: int
    model_config = ConfigDict(from_attributes=True)


class AulaDetalleOut(BaseModel):
    id_aula: int
    nombre: str
    ubicacion: str | None = None
    capacidad: int
    activa: bool
    total_asientos: int = 0
    asientos_habilitados: int = 0

router = APIRouter(prefix="/admin", tags=["Administración"])

# USUARIOS
@router.post("/usuarios", response_model=UsuarioOut)
def crear_usuario(
    payload: UsuarioCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_super_admin)
):
    if db.query(Usuario).filter(Usuario.usuario == payload.usuario).first():
        raise HTTPException(status_code=400, detail="El usuario ya existe")
    
    nuevo_usuario = Usuario(
        nombre_completo=payload.nombre_completo,
        genero=payload.genero,
        usuario=payload.usuario,
        password_hash=get_password_hash(payload.password),
        rol=payload.rol,
        activo=payload.activo
    )
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    registrar_auditoria(db, admin.id_usuario, "CREAR_USUARIO", "usuarios", f"Usuario {nuevo_usuario.usuario}")
    return nuevo_usuario


@router.get("/usuarios", response_model=List[UsuarioOut])
def listar_usuarios(
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_super_admin)
):
    return db.query(Usuario).order_by(Usuario.usuario).all()


@router.patch("/usuarios/{id_usuario}", response_model=UsuarioOut)
def actualizar_usuario(
    id_usuario: int,
    payload: UsuarioUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_super_admin)
):
    usuario = db.query(Usuario).filter(Usuario.id_usuario == id_usuario).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    cambios = payload.model_dump(exclude_unset=True)
    password = cambios.pop("password", None)
    if password:
        cambios["password_hash"] = get_password_hash(password)
    for campo, valor in cambios.items():
        setattr(usuario, campo, valor)
    db.commit()
    db.refresh(usuario)
    registrar_auditoria(db, admin.id_usuario, "ACTUALIZAR_USUARIO", "usuarios", f"Usuario {usuario.usuario}")
    return usuario

# CARRERAS
@router.post("/carreras", response_model=CarreraOut)
def crear_carrera(payload: CarreraCreate, db: Session = Depends(get_db), admin: Usuario = Depends(get_current_user)):
    carrera = Carrera(**payload.model_dump())
    db.add(carrera)
    db.commit()
    db.refresh(carrera)
    registrar_auditoria(db, admin.id_usuario, "CREAR_CARRERA", "carreras", f"Carrera {carrera.nombre}")
    return carrera

@router.get("/carreras", response_model=List[CarreraOut])
def listar_carreras(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    return db.query(Carrera).all()

@router.patch("/carreras/{id_carrera}", response_model=CarreraOut)
def actualizar_carrera(
    id_carrera: int,
    payload: CarreraUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user)
):
    carrera = db.query(Carrera).filter(Carrera.id_carrera == id_carrera).first()
    if not carrera:
        raise HTTPException(status_code=404, detail="Carrera no encontrada")
    cambios = payload.model_dump(exclude_unset=True)
    if "nombre" in cambios and not cambios["nombre"].strip():
        raise HTTPException(status_code=422, detail="El nombre no puede estar vacío")
    if "codigo" in cambios:
        # El código es opcional: vacío significa «sin código», igual que las
        # carreras que se dan de alta solas desde la carga masiva.
        cambios["codigo"] = str(cambios["codigo"]).strip() or None
    for campo, valor in cambios.items():
        setattr(carrera, campo, valor)
    db.commit()
    db.refresh(carrera)
    registrar_auditoria(db, admin.id_usuario, "ACTUALIZAR_CARRERA", "carreras", f"Carrera {carrera.nombre}")
    return carrera

# GESTIONES
@router.post("/gestiones", response_model=GestionOut)
def crear_gestion(payload: GestionCreate, db: Session = Depends(get_db), admin: Usuario = Depends(get_current_user)):
    if payload.fecha_fin < payload.fecha_inicio:
        raise HTTPException(status_code=422, detail="La fecha fin no puede ser anterior a la fecha inicio")
    if db.query(Gestion).filter(Gestion.nombre == payload.nombre).first():
        raise HTTPException(status_code=409, detail="Ya existe una gestión con ese nombre")
    gestion = Gestion(**payload.model_dump())
    db.add(gestion)
    db.commit()
    db.refresh(gestion)
    registrar_auditoria(db, admin.id_usuario, "CREAR_GESTION", "gestiones", f"Gestión {gestion.nombre}")
    return gestion

@router.get("/gestiones", response_model=List[GestionOut])
def listar_gestiones(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    return db.query(Gestion).all()

@router.patch("/gestiones/{id_gestion}", response_model=GestionOut)
def actualizar_gestion(
    id_gestion: int,
    payload: GestionUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user)
):
    gestion = db.query(Gestion).filter(Gestion.id_gestion == id_gestion).first()
    if not gestion:
        raise HTTPException(status_code=404, detail="Gestión no encontrada")
    cambios = payload.model_dump(exclude_unset=True)

    fecha_inicio = cambios.get("fecha_inicio", gestion.fecha_inicio)
    fecha_fin = cambios.get("fecha_fin", gestion.fecha_fin)
    if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
        raise HTTPException(status_code=422, detail="La fecha fin no puede ser anterior a la fecha inicio")

    nuevo_nombre = cambios.get("nombre")
    if nuevo_nombre is not None:
        if not nuevo_nombre.strip():
            raise HTTPException(status_code=422, detail="El nombre no puede estar vacío")
        duplicada = db.query(Gestion).filter(
            Gestion.nombre == nuevo_nombre,
            Gestion.id_gestion != id_gestion
        ).first()
        if duplicada:
            raise HTTPException(status_code=409, detail="Ya existe una gestión con ese nombre")

    for campo, valor in cambios.items():
        setattr(gestion, campo, valor)
    db.commit()
    db.refresh(gestion)
    registrar_auditoria(db, admin.id_usuario, "ACTUALIZAR_GESTION", "gestiones", f"Gestión {gestion.nombre}")
    return gestion

# AULAS Y ASIENTOS
@router.post("/aulas", response_model=AulaOut)
def crear_aula(payload: AulaCreate, db: Session = Depends(get_db), admin: Usuario = Depends(get_current_user)):
    data = payload.model_dump()
    generar_auto = data.pop("generar_asientos_auto", True)
    aula = Aula(**data)
    db.add(aula)
    db.flush()

    if generar_auto:
        asientos = [
            Asiento(id_aula=aula.id_aula, numero_asiento=i, habilitado=True)
            for i in range(1, aula.capacidad + 1)
        ]
        db.bulk_save_objects(asientos)

    db.commit()
    db.refresh(aula)
    registrar_auditoria(db, admin.id_usuario, "CREAR_AULA", "aulas", f"Aula {aula.nombre} con capacidad {aula.capacidad}")
    return aula

@router.get("/aulas/{id_aula}/asientos", response_model=List[AsientoOut])
def listar_asientos(id_aula: int, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    return db.query(Asiento).filter(Asiento.id_aula == id_aula).order_by(Asiento.numero_asiento).all()


@router.post("/aulas/{id_aula}/asientos", response_model=List[AsientoOut])
def crear_asientos(
    id_aula: int,
    payload: AsientosCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_super_admin)
):
    aula = db.query(Aula).filter(Aula.id_aula == id_aula).first()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")
    existentes = {
        asiento.numero_asiento for asiento in db.query(Asiento).filter(
            Asiento.id_aula == id_aula
        ).all()
    }
    nuevos = []
    for numero in range(payload.numero_inicial, payload.numero_inicial + payload.cantidad):
        if numero not in existentes:
            nuevos.append(Asiento(
                id_aula=id_aula,
                numero_asiento=numero,
                habilitado=True
            ))
    if not nuevos:
        raise HTTPException(status_code=409, detail="Todos los números solicitados ya existen")
    db.add_all(nuevos)
    db.commit()
    for asiento in nuevos:
        db.refresh(asiento)
    registrar_auditoria(
        db, admin.id_usuario, "CREAR_ASIENTOS", "asientos",
        f"Aula {aula.nombre}: {len(nuevos)} asientos creados"
    )
    return nuevos


@router.patch("/aulas/{id_aula}", response_model=AulaOut)
def actualizar_aula(
    id_aula: int,
    payload: AulaUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_super_admin)
):
    from app.models.asignacion import Asignacion
    aula = db.query(Aula).filter(Aula.id_aula == id_aula).first()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")
    cambios = payload.model_dump(exclude_unset=True)
    if "capacidad" in cambios and cambios["capacidad"] <= 0:
        raise HTTPException(status_code=422, detail="La capacidad debe ser mayor que cero")

    # Sincronizar la cantidad de asientos con la capacidad indicada.
    if "capacidad" in cambios:
        objetivo = cambios["capacidad"]
        asientos = db.query(Asiento).filter(
            Asiento.id_aula == id_aula
        ).order_by(Asiento.numero_asiento).all()
        actual = len(asientos)

        if objetivo > actual:
            # Agregar los asientos faltantes con numeración consecutiva.
            usados = {a.numero_asiento for a in asientos}
            numero = (max(usados) + 1) if usados else 1
            for _ in range(objetivo - actual):
                while numero in usados:
                    numero += 1
                db.add(Asiento(id_aula=id_aula, numero_asiento=numero, habilitado=True))
                usados.add(numero)
                numero += 1
        elif objetivo < actual:
            # Quitar los asientos de numeración más alta, salvo que tengan asignaciones.
            a_eliminar = asientos[objetivo:]
            con_asignacion = [
                a for a in a_eliminar
                if db.query(Asignacion).filter(Asignacion.id_asiento == a.id_asiento).first()
            ]
            if con_asignacion:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "No se puede reducir la capacidad: "
                        f"{len(con_asignacion)} asiento(s) a eliminar tienen asignaciones de exámenes."
                    )
                )
            for a in a_eliminar:
                db.delete(a)

    for campo, valor in cambios.items():
        setattr(aula, campo, valor)
    db.commit()
    db.refresh(aula)
    registrar_auditoria(
        db, admin.id_usuario, "ACTUALIZAR_AULA", "aulas",
        f"Aula {aula.nombre} (capacidad {aula.capacidad})"
    )
    return aula


@router.patch("/asientos/{id_asiento}/habilitado", response_model=AsientoOut)
def cambiar_estado_asiento(
    id_asiento: int,
    habilitado: bool,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_super_admin)
):
    asiento = db.query(Asiento).filter(Asiento.id_asiento == id_asiento).first()
    if not asiento:
        raise HTTPException(status_code=404, detail="Asiento no encontrado")
    asiento.habilitado = habilitado
    db.commit()
    db.refresh(asiento)
    registrar_auditoria(db, admin.id_usuario, "CAMBIAR_ASIENTO", "asientos", f"Asiento {id_asiento}: {habilitado}")
    return asiento


@router.patch("/asientos/{id_asiento}", response_model=AsientoOut)
def actualizar_asiento(
    id_asiento: int,
    payload: AsientoUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_super_admin)
):
    asiento = db.query(Asiento).filter(Asiento.id_asiento == id_asiento).first()
    if not asiento:
        raise HTTPException(status_code=404, detail="Asiento no encontrado")
    cambios = payload.model_dump(exclude_unset=True)
    if "numero_asiento" in cambios and cambios["numero_asiento"] <= 0:
        raise HTTPException(status_code=422, detail="El número de asiento debe ser mayor que cero")
    if "numero_asiento" in cambios and cambios["numero_asiento"] != asiento.numero_asiento:
        duplicado = db.query(Asiento).filter(
            Asiento.id_aula == asiento.id_aula,
            Asiento.numero_asiento == cambios["numero_asiento"],
            Asiento.id_asiento != id_asiento
        ).first()
        if duplicado:
            raise HTTPException(status_code=409, detail="Ya existe un asiento con ese número en el aula")
    for campo, valor in cambios.items():
        setattr(asiento, campo, valor)
    db.commit()
    db.refresh(asiento)
    registrar_auditoria(db, admin.id_usuario, "ACTUALIZAR_ASIENTO", "asientos", f"Asiento {id_asiento}")
    return asiento


@router.delete("/asientos/{id_asiento}", status_code=204)
def eliminar_asiento(
    id_asiento: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_super_admin)
):
    from app.models.asignacion import Asignacion
    asiento = db.query(Asiento).filter(Asiento.id_asiento == id_asiento).first()
    if not asiento:
        raise HTTPException(status_code=404, detail="Asiento no encontrado")
    asignaciones = db.query(Asignacion).filter(Asignacion.id_asiento == id_asiento).count()
    if asignaciones:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede eliminar: el asiento tiene {asignaciones} asignación(es). Deshabilítelo en su lugar."
        )
    db.delete(asiento)
    db.commit()
    registrar_auditoria(db, admin.id_usuario, "ELIMINAR_ASIENTO", "asientos", f"Asiento {id_asiento}")


@router.get("/aulas", response_model=List[AulaDetalleOut])
def listar_aulas(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    aulas = db.query(Aula).order_by(Aula.nombre).all()
    resultado = []
    for aula in aulas:
        total = db.query(Asiento).filter(Asiento.id_aula == aula.id_aula).count()
        habilitados = db.query(Asiento).filter(
            Asiento.id_aula == aula.id_aula,
            Asiento.habilitado.is_(True)
        ).count()
        resultado.append(AulaDetalleOut(
            id_aula=aula.id_aula,
            nombre=aula.nombre,
            ubicacion=aula.ubicacion,
            capacidad=aula.capacidad,
            activa=aula.activa,
            total_asientos=total,
            asientos_habilitados=habilitados,
        ))
    return resultado


@router.get("/aulas/{id_aula}", response_model=AulaDetalleOut)
def detalle_aula(id_aula: int, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    aula = db.query(Aula).filter(Aula.id_aula == id_aula).first()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")
    total = db.query(Asiento).filter(Asiento.id_aula == aula.id_aula).count()
    habilitados = db.query(Asiento).filter(
        Asiento.id_aula == aula.id_aula,
        Asiento.habilitado.is_(True)
    ).count()
    return AulaDetalleOut(
        id_aula=aula.id_aula,
        nombre=aula.nombre,
        ubicacion=aula.ubicacion,
        capacidad=aula.capacidad,
        activa=aula.activa,
        total_asientos=total,
        asientos_habilitados=habilitados,
    )


@router.delete("/aulas/{id_aula}", status_code=204)
def eliminar_aula(
    id_aula: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_super_admin)
):
    from app.models.asignacion import Asignacion
    aula = db.query(Aula).filter(Aula.id_aula == id_aula).first()
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")
    asignaciones = db.query(Asignacion).filter(Asignacion.id_aula == id_aula).count()
    if asignaciones:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede eliminar: el aula tiene {asignaciones} asignación(es) de exámenes. Deshabilítela en su lugar."
        )
    nombre = aula.nombre
    db.delete(aula)
    db.commit()
    registrar_auditoria(db, admin.id_usuario, "ELIMINAR_AULA", "aulas", f"Aula {nombre}")

# EXAMENES
@router.post("/examenes", response_model=ExamenOut)
def crear_examen(payload: ExamenCreate, db: Session = Depends(get_db), admin: Usuario = Depends(get_current_user)):
    if payload.hora_fin <= payload.hora_inicio:
        raise HTTPException(status_code=400, detail="La hora fin debe ser posterior a la de inicio")
    carrera = db.query(Carrera).filter(Carrera.id_carrera == payload.id_carrera).first()
    if not carrera:
        raise HTTPException(status_code=404, detail="Carrera no encontrada")
    if not carrera.activa:
        raise HTTPException(status_code=409, detail="La carrera está inactiva")
    gestion = db.query(Gestion).filter(Gestion.id_gestion == payload.id_gestion).first()
    if not gestion:
        raise HTTPException(status_code=404, detail="Gestión no encontrada")
    if payload.fecha < gestion.fecha_inicio or payload.fecha > gestion.fecha_fin:
        raise HTTPException(status_code=422, detail="La fecha del examen está fuera del rango de la gestión")
    examen = Examen(**payload.model_dump())
    db.add(examen)
    db.commit()
    db.refresh(examen)
    registrar_auditoria(db, admin.id_usuario, "CREAR_EXAMEN", "examenes", f"Materia {examen.materia}")
    return examen


@router.get("/examenes", response_model=List[ExamenOut])
def listar_examenes(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    return db.query(Examen).order_by(Examen.fecha.desc(), Examen.hora_inicio).all()

@router.patch("/examenes/{id_examen}", response_model=ExamenOut)
def actualizar_examen(
    id_examen: int,
    payload: ExamenUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user)
):
    examen = db.query(Examen).filter(Examen.id_examen == id_examen).first()
    if not examen:
        raise HTTPException(status_code=404, detail="Examen no encontrado")
    cambios = payload.model_dump(exclude_unset=True)

    id_carrera = cambios.get("id_carrera", examen.id_carrera)
    id_gestion = cambios.get("id_gestion", examen.id_gestion)
    carrera = db.query(Carrera).filter(Carrera.id_carrera == id_carrera).first()
    if not carrera:
        raise HTTPException(status_code=404, detail="Carrera no encontrada")
    if not carrera.activa:
        raise HTTPException(status_code=409, detail="La carrera está inactiva")
    gestion = db.query(Gestion).filter(Gestion.id_gestion == id_gestion).first()
    if not gestion:
        raise HTTPException(status_code=404, detail="Gestión no encontrada")

    hora_inicio = cambios.get("hora_inicio", examen.hora_inicio)
    hora_fin = cambios.get("hora_fin", examen.hora_fin)
    if hora_fin <= hora_inicio:
        raise HTTPException(status_code=400, detail="La hora fin debe ser posterior a la de inicio")

    fecha = cambios.get("fecha", examen.fecha)
    if gestion.fecha_inicio and gestion.fecha_fin and (
        fecha < gestion.fecha_inicio or fecha > gestion.fecha_fin
    ):
        raise HTTPException(status_code=422, detail="La fecha del examen está fuera del rango de la gestión")

    for campo, valor in cambios.items():
        setattr(examen, campo, valor)
    db.commit()
    db.refresh(examen)
    registrar_auditoria(db, admin.id_usuario, "ACTUALIZAR_EXAMEN", "examenes", f"Materia {examen.materia}")
    return examen


@router.get("/auditoria")
def listar_auditoria(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    accion: str | None = Query(None, max_length=100),
    entidad: str | None = Query(None, max_length=100),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_super_admin)
):
    query = db.query(Auditoria)
    if accion:
        query = query.filter(Auditoria.accion.ilike(f"%{accion}%"))
    if entidad:
        query = query.filter(Auditoria.entidad_afectada.ilike(f"%{entidad}%"))
    registros = query.order_by(Auditoria.fecha_hora.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id_auditoria": registro.id_auditoria,
            "id_usuario": registro.id_usuario,
            "accion": registro.accion,
            "entidad_afectada": registro.entidad_afectada,
            "detalle": registro.detalle,
            "fecha_hora": registro.fecha_hora,
        }
        for registro in registros
    ]
