from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user, require_super_admin, registrar_auditoria
from app.models.usuario import Usuario
from app.models.postulante import Postulante, OrigenRegistro
from app.models.marcacion import RegistroIngreso
from app.models.asignacion import Asignacion
from app.models.academico import Carrera, Gestion, Inscripcion
from app.models.biometria import Rostro, Huella
from app.schemas.postulante import PostulanteCreate, PostulanteUpdate, PostulanteResponse
from app.services.importacion_excel import leer_postulantes, normalizar

router = APIRouter(prefix="/postulantes", tags=["Postulantes"])

# Máximo de carreras en las que un postulante puede inscribirse por gestión.
MAXIMO_CARRERAS = 2


def _respuesta_con_biometria(
    postulante: Postulante, rostro, cantidad_huellas: int
) -> PostulanteResponse:
    return PostulanteResponse(
        id_postulante=postulante.id_postulante,
        ci=postulante.ci,
        nombres=postulante.nombres,
        apellidos=postulante.apellidos,
        genero=postulante.genero,
        telefono=postulante.telefono,
        correo=postulante.correo,
        direccion=postulante.direccion,
        fecha_nacimiento=postulante.fecha_nacimiento,
        estado_biometria=str(postulante.estado_biometria) if postulante.estado_biometria else "PENDIENTE",
        origen_registro=str(postulante.origen_registro) if postulante.origen_registro else "MANUAL",
        fecha_registro=postulante.fecha_registro,
        tiene_rostro=bool(rostro and rostro.habilitada),
        rostro_registrado=rostro is not None,
        id_rostro=rostro.id_rostro if rostro else None,
        cantidad_huellas=cantidad_huellas
    )


def _postulante_response(db: Session, postulante: Postulante) -> PostulanteResponse:
    rostro = db.query(Rostro).filter(
        Rostro.id_postulante == postulante.id_postulante
    ).order_by(Rostro.fecha_registro.desc()).first()
    cantidad_huellas = db.query(Huella).filter(
        Huella.id_postulante == postulante.id_postulante
    ).count()
    return _respuesta_con_biometria(postulante, rostro, cantidad_huellas)


def _postulantes_response_bulk(
    db: Session, postulantes: List[Postulante]
) -> List[PostulanteResponse]:
    """Igual que _postulante_response pero en 2 consultas (no 2 por fila).

    Con 1000+ postulantes el N+1 tardaba segundos en abrir el panel.
    """
    ids = [p.id_postulante for p in postulantes]
    if not ids:
        return []
    rostros = db.query(Rostro).filter(
        Rostro.id_postulante.in_(ids)
    ).order_by(
        Rostro.id_postulante,
        Rostro.fecha_registro.desc(),
        Rostro.id_rostro.desc(),
    ).all()
    ultimo = {}
    for rostro in rostros:
        ultimo.setdefault(rostro.id_postulante, rostro)
    conteos = dict(db.query(
        Huella.id_postulante, func.count(Huella.id_huella)
    ).filter(
        Huella.id_postulante.in_(ids)
    ).group_by(Huella.id_postulante).all())
    return [
        _respuesta_con_biometria(
            p, ultimo.get(p.id_postulante), int(conteos.get(p.id_postulante, 0))
        )
        for p in postulantes
    ]


@router.get("", response_model=List[PostulanteResponse])
@router.get("/", response_model=List[PostulanteResponse], include_in_schema=False)
def listar_postulantes(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1),
    q: Optional[str] = Query(None, min_length=1),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user)
):
    consulta = db.query(Postulante)
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.filter(or_(
            Postulante.ci.ilike(patron),
            Postulante.nombres.ilike(patron),
            Postulante.apellidos.ilike(patron),
            func.concat(
                Postulante.nombres, " ", Postulante.apellidos
            ).ilike(patron),
        ))
    postulantes = consulta.offset(skip).limit(limit).all()
    return _postulantes_response_bulk(db, postulantes)

@router.get("/buscar", response_model=PostulanteResponse)
def buscar_postulante_por_ci(
    ci: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    ci_limpio = ci.strip()
    postulante = db.query(Postulante).filter(Postulante.ci == ci_limpio).first()
    if not postulante:
        raise HTTPException(status_code=404, detail="Postulante no encontrado")
    return _postulante_response(db, postulante)

@router.post("", response_model=PostulanteResponse)
@router.post("/", response_model=PostulanteResponse, include_in_schema=False)
def crear_postulante(
    payload: PostulanteCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user)
):
    ci_limpio = payload.ci.strip()
    existe = db.query(Postulante).filter(Postulante.ci == ci_limpio).first()
    if existe:
        raise HTTPException(status_code=400, detail=f"Ya existe un postulante con C.I. {ci_limpio}")

    nuevo = Postulante(
        ci=ci_limpio,
        nombres=payload.nombres.strip(),
        apellidos=payload.apellidos.strip(),
        genero=payload.genero,
        telefono=payload.telefono,
        correo=payload.correo,
        direccion=payload.direccion,
        fecha_nacimiento=payload.fecha_nacimiento,
        estado_biometria="PENDIENTE",
        origen_registro="MANUAL"
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)

    try:
        registrar_auditoria(db, admin.id_usuario, "CREAR_POSTULANTE", "postulantes", f"Postulante CI {nuevo.ci} registrado")
    except Exception:
        pass

    return _postulante_response(db, nuevo)


@router.get("/estadisticas")
def estadisticas_postulantes(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    """Conteo por estado biométrico (para el panel, sin traer miles de filas)."""
    filas = db.query(
        Postulante.estado_biometria, func.count(Postulante.id_postulante)
    ).group_by(Postulante.estado_biometria).all()
    return {
        (estado.value if hasattr(estado, "value") else str(estado or "PENDIENTE")):
            int(total)
        for estado, total in filas
    }


@router.patch("/{id_postulante}", response_model=PostulanteResponse)
def actualizar_postulante(
    id_postulante: int,
    payload: PostulanteUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user)
):
    postulante = db.query(Postulante).filter(Postulante.id_postulante == id_postulante).first()
    if not postulante:
        raise HTTPException(status_code=404, detail="Postulante no encontrado")

    cambios = payload.model_dump(exclude_unset=True)
    if "nombres" in cambios:
        cambios["nombres"] = cambios["nombres"].strip()
    if "apellidos" in cambios:
        cambios["apellidos"] = cambios["apellidos"].strip()
    for campo, valor in cambios.items():
        if isinstance(valor, str) and not valor:
            raise HTTPException(status_code=422, detail=f"El campo {campo} no puede estar vacío")
        setattr(postulante, campo, valor)
    db.commit()
    db.refresh(postulante)
    registrar_auditoria(db, admin.id_usuario, "ACTUALIZAR_POSTULANTE", "postulantes", f"CI {postulante.ci}")
    return _postulante_response(db, postulante)


@router.delete("/{id_postulante}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_postulante(
    id_postulante: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_super_admin)
):
    postulante = db.query(Postulante).filter(Postulante.id_postulante == id_postulante).first()
    if not postulante:
        raise HTTPException(status_code=404, detail="Postulante no encontrado")

    ci = postulante.ci
    inscripciones = db.query(Inscripcion).filter(
        Inscripcion.id_postulante == id_postulante
    ).all()
    ids_inscripcion = [inscripcion.id_inscripcion for inscripcion in inscripciones]
    ids_asignacion = [
        id_asignacion
        for (id_asignacion,) in db.query(Asignacion.id_asignacion).filter(
            Asignacion.id_inscripcion.in_(ids_inscripcion)
        ).all()
    ] if ids_inscripcion else []

    # Conserva el historial de marcaciones, pero evita que sus FK bloqueen
    # la eliminación de la inscripción y de sus asignaciones.
    if ids_inscripcion:
        db.query(RegistroIngreso).filter(
            RegistroIngreso.id_inscripcion.in_(ids_inscripcion)
        ).update(
            {"id_inscripcion": None},
            synchronize_session=False,
        )
    if ids_asignacion:
        db.query(RegistroIngreso).filter(
            RegistroIngreso.id_asignacion.in_(ids_asignacion)
        ).update(
            {"id_asignacion": None},
            synchronize_session=False,
        )

    try:
        db.delete(postulante)
        db.commit()
    except Exception:
        db.rollback()
        raise

    registrar_auditoria(db, admin.id_usuario, "ELIMINAR_POSTULANTE", "postulantes", f"CI {ci}")

def _completar_vacios(postulante: Postulante, fila: dict) -> bool:
    """Rellena con el Excel sólo los campos que el postulante tenía vacíos.

    Nunca pisa datos cargados a mano ni por una importación anterior.
    """
    relleno = False
    for campo in ("apellidos", "genero", "fecha_nacimiento", "telefono", "correo", "direccion"):
        if getattr(postulante, campo, None) in (None, "") and fila.get(campo):
            setattr(postulante, campo, fila[campo])
            relleno = True
    if not postulante.nombres and fila.get("nombres"):
        postulante.nombres = fila["nombres"]
        relleno = True
    return relleno


@router.post("/importar-excel")
async def importar_excel_postulantes(
    file: UploadFile = File(...),
    id_gestion: Optional[int] = Form(None),
    id_carrera: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    admin: Usuario = Depends(get_current_user)
):
    """Carga masiva de postulantes desde un archivo Excel.

    Cada fila del archivo equivale a una inscripción: un mismo CI puede
    aparecer dos veces si el postulante se inscribió en dos carreras, que es
    el máximo permitido. La carrera de cada fila sale de la columna
    «programa» y se da de alta si todavía no existe. Si el archivo no trae
    esa columna, hay que indicar ``id_carrera``.
    """
    contents = await file.read()
    nombre_archivo = file.filename or ""
    try:
        filas, columnas = leer_postulantes(contents, nombre_archivo)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo: {error}")

    if not filas:
        raise HTTPException(status_code=400, detail="El archivo no tiene filas con documento y nombre.")
    if "ci" not in columnas.values() or "nombres" not in columnas.values():
        encabezados = ", ".join(str(c) for c in columnas) or "(ninguno)"
        raise HTTPException(
            status_code=400,
            detail=f"No se encontraron las columnas de documento y nombre. Encabezados del archivo: {encabezados}"
        )
    if "programa" not in columnas.values() and id_carrera is None:
        raise HTTPException(
            status_code=400,
            detail="El archivo no tiene la columna «programa» (carrera). Indique la carrera a inscribir.",
            headers={"X-Codigo-Error": "falta-carrera"}
        )

    gestion = db.get(Gestion, id_gestion) if id_gestion else None
    if gestion is None:
        gestion = db.query(Gestion).order_by(Gestion.id_gestion.desc()).first()
    if gestion is None:
        raise HTTPException(status_code=400, detail="No hay gestiones registradas.")

    carrera_fija = db.get(Carrera, id_carrera) if id_carrera else None
    if id_carrera and carrera_fija is None:
        raise HTTPException(status_code=404, detail="Carrera no encontrada")

    # Catálogo de carreras en memoria: el Excel trae el nombre en texto y hay
    # que resolverlo sin cargarlo fila por fila.
    catalogo = {}
    for carrera in db.query(Carrera).all():
        catalogo[normalizar(carrera.nombre)] = carrera
        if carrera.codigo:
            catalogo[normalizar(carrera.codigo)] = carrera

    carreras_creadas = []

    def _carrera_de(nombre_carrera: str):
        clave = normalizar(nombre_carrera)
        if not clave:
            return None
        encontrada = catalogo.get(clave)
        if encontrada is not None:
            return encontrada
        nueva = Carrera(nombre=nombre_carrera.strip(), activa=True)
        db.add(nueva)
        db.flush()
        catalogo[clave] = nueva
        carreras_creadas.append(nueva.nombre)
        return nueva

    creados = actualizados = sin_carrera = limitados = 0
    inscripciones_nuevas = inscripciones_existentes = 0
    avisos = []

    try:
        for fila in filas:
            ci = fila["ci"].strip()
            postulante = db.query(Postulante).filter(Postulante.ci == ci).first()
            if postulante is None:
                postulante = Postulante(
                    ci=ci,
                    nombres=fila["nombres"],
                    # Sin apellidos el campo no nulo rompería la carga entera.
                    apellidos=fila.get("apellidos") or fila["nombres"],
                    genero=fila.get("genero"),
                    fecha_nacimiento=fila.get("fecha_nacimiento"),
                    telefono=fila.get("telefono"),
                    correo=fila.get("correo"),
                    direccion=fila.get("direccion"),
                    estado_biometria="PENDIENTE",
                    origen_registro=OrigenRegistro.EXCEL
                )
                db.add(postulante)
                db.flush()
                creados += 1
            elif _completar_vacios(postulante, fila):
                actualizados += 1

            carrera = _carrera_de(fila.get("programa") or (carrera_fija.nombre if carrera_fija else ""))
            if carrera is None:
                sin_carrera += 1
                avisos.append(f"CI {ci}: sin carrera, no se pudo inscribir.")
                continue

            ya_inscrita = db.query(Inscripcion).filter(
                Inscripcion.id_postulante == postulante.id_postulante,
                Inscripcion.id_gestion == gestion.id_gestion,
                Inscripcion.id_carrera == carrera.id_carrera
            ).first()
            if ya_inscrita:
                inscripciones_existentes += 1
                continue

            total_carreras = db.query(Inscripcion).filter(
                Inscripcion.id_postulante == postulante.id_postulante,
                Inscripcion.id_gestion == gestion.id_gestion,
                Inscripcion.estado != "RETIRADO"
            ).count()
            if total_carreras >= MAXIMO_CARRERAS:
                limitados += 1
                avisos.append(
                    f"{postulante.ci} {postulante.nombres}: ya tiene {total_carreras} carreras "
                    f"inscritas, no se agregó «{carrera.nombre}»."
                )
                continue

            db.add(Inscripcion(
                id_postulante=postulante.id_postulante,
                id_gestion=gestion.id_gestion,
                id_carrera=carrera.id_carrera,
                estado="HABILITADO"
            ))
            # Sin flush la siguiente fila no ve esta inscripción y duplicaría el conteo.
            db.flush()
            inscripciones_nuevas += 1

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al procesar archivo Excel: {error}")

    mensaje = (
        f"Se procesaron {len(filas)} filas: {creados} postulantes nuevos, "
        f"{actualizados} completados y {inscripciones_nuevas} inscripciones nuevas en {gestion.nombre}."
    )
    if carreras_creadas:
        mensaje += f" Carreras dadas de alta: {', '.join(carreras_creadas)}."
    if limitados:
        mensaje += f" {limitados} postulante(s) ya tenían {MAXIMO_CARRERAS} carreras y no se agregó más."
    if avisos:
        mensaje += " Revisa los avisos del detalle."

    try:
        registrar_auditoria(db, admin.id_usuario, "IMPORTAR_EXCEL", "postulantes", mensaje)
    except Exception:
        pass

    return {
        "mensaje": mensaje,
        "filas_leidas": len(filas),
        "creados": creados,
        "actualizados": actualizados,
        "inscripciones_nuevas": inscripciones_nuevas,
        "inscripciones_existentes": inscripciones_existentes,
        "inscripciones_rechazadas_por_limite": limitados,
        "filas_sin_carrera": sin_carrera,
        "carreras_creadas": carreras_creadas,
        "columnas_detectadas": {str(col): campo for col, campo in columnas.items()},
        "avisos": avisos[:50]
    }
