import base64
from datetime import datetime, timedelta, time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct

from app.core.database import get_db
from app.api.deps import require_app_key
from app.models.usuario import Usuario
from app.models.postulante import Postulante
from app.models.biometria import Rostro, Huella
from app.models.academico import Examen
from app.models.asignacion import Asignacion, Inscripcion
from app.models.infraestructura import Aula, Asiento
from app.models.marcacion import RegistroIngreso, MetodoMarcacion, ResultadoMarcacion
from app.schemas.marcacion import MarcacionRespuestaOut, ContadorTiempoRealOut
from app.services.face_service import face_service
from app.services.fingerprint_service import fingerprint_service

router = APIRouter(prefix="/marcaciones", tags=["Control de Acceso y Marcación"])
active_router = APIRouter(prefix="/examenes/activos-ahora", tags=["Control de Acceso y Marcación"])
marking_router = APIRouter(prefix="/marcacion", tags=["Control de Acceso y Marcación"])

# Umbral de similitud (score 0-100) que el cliente debe alcanzar para que
# el servidor confíe en la verificación hecha localmente con la SDK del lector.
UMBRAL_HUELLA_CLIENTE = 60

def validar_cuatro_reglas_y_registrar(
    db: Session,
    id_examen: int,
    postulante: Optional[Postulante],
    metodo: MetodoMarcacion,
    score: Optional[float],
    cliente: str = "APP_CLIENT",
) -> MarcacionRespuestaOut:
    ahora = datetime.now()
    fecha_actual = ahora.date()
    hora_actual = ahora.time()

    # 1. Regla 1: Identificación Biométrica
    if not postulante:
        reg = RegistroIngreso(
            metodo=metodo,
            resultado=ResultadoMarcacion.RECHAZADO,
            score_similitud=score,
            fecha_hora=ahora,
            estacion=cliente,
            observacion="RECHAZO REGLA 1: No se reconoció la identidad biométrica"
        )
        db.add(reg)
        db.commit()
        return MarcacionRespuestaOut(
            resultado=ResultadoMarcacion.RECHAZADO,
            metodo=metodo,
            mensaje="Identidad no reconocida en el sistema",
            score_similitud=score,
            fecha_hora=ahora
        )

    # 2. Regla 2 y 3: Inscripción Vigente en la Gestión y Carrera del Examen
    examen = db.query(Examen).filter(Examen.id_examen == id_examen).first()
    if not examen:
        raise HTTPException(status_code=404, detail="Examen no encontrado")

    inscripcion = db.query(Inscripcion).filter(
        Inscripcion.id_postulante == postulante.id_postulante,
        Inscripcion.id_gestion == examen.id_gestion,
        Inscripcion.id_carrera == examen.id_carrera,
        Inscripcion.estado == "HABILITADO"
    ).first()

    if not inscripcion:
        reg = RegistroIngreso(
            metodo=metodo,
            resultado=ResultadoMarcacion.RECHAZADO,
            score_similitud=score,
            fecha_hora=ahora,
            estacion=cliente,
            observacion=f"RECHAZO REGLAS 2/3: Postulante CI {postulante.ci} no cuenta con inscripción válida para la carrera/gestión del examen"
        )
        db.add(reg)
        db.commit()
        return MarcacionRespuestaOut(
            resultado=ResultadoMarcacion.RECHAZADO,
            metodo=metodo,
            id_postulante=postulante.id_postulante,
            ci=postulante.ci,
            nombre_completo=f"{postulante.nombres} {postulante.apellidos}",
            mensaje="El postulante no pertenece a la carrera o gestión de este examen",
            score_similitud=score,
            fecha_hora=ahora
        )

    # Obtener Asignación (Aula y Asiento) si ya se realizó el sorteo.
    # La asignación es OPCIONAL: la inscripción vigente es suficiente para
    # permitir el ingreso a cualquier examen de la carrera/gestión.
    asignacion = db.query(Asignacion).filter(
        Asignacion.id_inscripcion == inscripcion.id_inscripcion,
        Asignacion.id_examen == id_examen
    ).first()

    # 3. Regla 4: Ventana de Horario Permitido
    # Permitir ingreso desde 45 minutos antes del inicio hasta el fin del examen.
    dt_inicio = datetime.combine(examen.fecha, examen.hora_inicio) - timedelta(minutes=45)
    dt_fin = datetime.combine(examen.fecha, examen.hora_fin) + timedelta(
        minutes=examen.tolerancia_minutos or 0
    )

    if not (dt_inicio <= ahora <= dt_fin):
        reg = RegistroIngreso(
            id_asignacion=asignacion.id_asignacion if asignacion else None,
            id_examen=examen.id_examen,
            id_inscripcion=inscripcion.id_inscripcion,
            metodo=metodo,
            resultado=ResultadoMarcacion.RECHAZADO,
            score_similitud=score,
            fecha_hora=ahora,
            estacion=cliente,
            observacion=f"RECHAZO REGLA 4: Intento de ingreso fuera de horario ({examen.hora_inicio} a {examen.hora_fin})"
        )
        db.add(reg)
        db.commit()
        return MarcacionRespuestaOut(
            resultado=ResultadoMarcacion.RECHAZADO,
            metodo=metodo,
            id_postulante=postulante.id_postulante,
            ci=postulante.ci,
            nombre_completo=f"{postulante.nombres} {postulante.apellidos}",
            mensaje="Acceso denegado: Fuera del horario programado para el examen",
            score_similitud=score,
            fecha_hora=ahora
        )

    # Si ya tenía un ingreso aceptado previamente, informar
    ingreso_previo = db.query(RegistroIngreso).filter(
        RegistroIngreso.id_examen == examen.id_examen,
        RegistroIngreso.id_inscripcion == inscripcion.id_inscripcion,
        RegistroIngreso.resultado == ResultadoMarcacion.ACEPTADO
    ).first()

    aula = None
    asiento = None
    if asignacion:
        aula = db.query(Aula).filter(Aula.id_aula == asignacion.id_aula).first()
        asiento = db.query(Asiento).filter(Asiento.id_asiento == asignacion.id_asiento).first()

    # Registro exitoso
    reg = RegistroIngreso(
        id_asignacion=asignacion.id_asignacion if asignacion else None,
        id_examen=examen.id_examen,
        id_inscripcion=inscripcion.id_inscripcion,
        metodo=metodo,
        resultado=ResultadoMarcacion.ACEPTADO,
        score_similitud=score,
        fecha_hora=ahora,
        estacion=cliente,
        observacion="INGRESO AUTORIZADO" if not ingreso_previo else "RE-INGRESO AUTORIZADO"
    )
    db.add(reg)
    db.commit()

    return MarcacionRespuestaOut(
        resultado=ResultadoMarcacion.ACEPTADO,
        metodo=metodo,
        id_postulante=postulante.id_postulante,
        ci=postulante.ci,
        nombre_completo=f"{postulante.nombres} {postulante.apellidos}",
        aula=aula.nombre if aula else "Sin asignar",
        numero_asiento=asiento.numero_asiento if asiento else 0,
        mensaje="ACCESO CONCEDIDO - Bienvenido" if not ingreso_previo else "ACCESO YA REGISTRADO PREVIAMENTE",
        score_similitud=score,
        fecha_hora=ahora
    )


@router.get("/examenes-activos/postulantes")
@active_router.get("/postulantes")
def listar_postulantes_examenes_activos(
    busqueda: str = Query("", max_length=100),
    db: Session = Depends(get_db),
    _: None = Depends(require_app_key)
):
    ahora = datetime.now()
    candidatos = []
    examenes = db.query(Examen).filter(Examen.fecha == ahora.date()).all()
    for examen in examenes:
        inicio = datetime.combine(examen.fecha, examen.hora_inicio)
        cierre = datetime.combine(examen.fecha, examen.hora_fin) + timedelta(
            minutes=examen.tolerancia_minutos or 0
        )
        if not inicio <= ahora <= cierre:
            continue

        filas = db.query(Postulante, Inscripcion).join(
            Inscripcion, Inscripcion.id_postulante == Postulante.id_postulante
        ).filter(
            Inscripcion.id_gestion == examen.id_gestion,
            Inscripcion.id_carrera == examen.id_carrera,
            Inscripcion.estado == "HABILITADO"
        ).all()
        for postulante, inscripcion in filas:
            texto = f"{postulante.ci} {postulante.nombres} {postulante.apellidos}".lower()
            if busqueda.strip().lower() not in texto:
                continue
            asignacion = db.query(Asignacion).filter(
                Asignacion.id_inscripcion == inscripcion.id_inscripcion,
                Asignacion.id_examen == examen.id_examen
            ).first()
            huellas = db.query(Huella.tipo_dedo).filter(
                Huella.id_postulante == postulante.id_postulante,
                Huella.habilitada.is_(True)
            ).all()
            rostro = db.query(Rostro).filter(
                Rostro.id_postulante == postulante.id_postulante,
                Rostro.habilitada.is_(True)
            ).first()
            candidatos.append({
                "id_examen": examen.id_examen,
                "materia": examen.materia,
                "id_postulante": postulante.id_postulante,
                "ci": postulante.ci,
                "nombre_completo": f"{postulante.nombres} {postulante.apellidos}",
                "dedos_habilitados": [dedo[0] for dedo in huellas],
                "rostro_habilitado": rostro is not None,
                "aula": asignacion.aula.nombre if asignacion and asignacion.aula else "Sin asignar",
                "numero_asiento": asignacion.asiento.numero_asiento if asignacion and asignacion.asiento else None
            })
    return candidatos


@router.get("/plantilla-huella")
@marking_router.get("/plantilla-huella")
async def obtener_plantilla_huella(
    id_postulante: int = Query(...),
    tipo_dedo: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_app_key)
):
    """Devuelve la plantilla de huella guardada (bytes crudos) para que el
    cliente con lector ZKTeco pueda hacer la comparación 1:1 localmente."""
    if not 1 <= tipo_dedo <= 10:
        raise HTTPException(status_code=422, detail="tipo_dedo debe estar entre 1 y 10")
    huella = db.query(Huella).filter(
        Huella.id_postulante == id_postulante,
        Huella.tipo_dedo == tipo_dedo,
        Huella.habilitada.is_(True)
    ).first()
    if not huella:
        raise HTTPException(
            status_code=404,
            detail="No hay plantilla de huella habilitada para ese dedo"
        )
    return Response(content=huella.plantilla_biometrica, media_type="application/octet-stream")


@router.get("/plantillas-examen")
@marking_router.get("/plantillas-examen")
def obtener_plantillas_examen(
    id_examen: Optional[int] = Query(None),
    limite: int = Query(300, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: None = Depends(require_app_key)
):
    """Devuelve las huellas **habilitadas** de los postulantes del examen.

    Es lo que permite la identificación automática: el cliente baja esta
    lista, apoya el dedo en el lector y va probando plantilla por plantilla
    hasta encontrar a quién pertenece, sin que el postulante tenga que
    buscar su nombre antes.

    Los postulantes que sí tienen huellas registradas pero ninguna
    habilitada vuelven aparte en ``sin_habilitar``, para que la estación
    pueda avisarles en vez de mostrar un "no reconocido" confuso.
    """
    ahora = datetime.now()

    examenes = []
    if id_examen:
        elegido = db.query(Examen).filter(Examen.id_examen == id_examen).first()
        if elegido:
            examenes.append(elegido)
    for examen in db.query(Examen).filter(Examen.fecha == ahora.date()).all():
        if all(examen.id_examen != e.id_examen for e in examenes):
            examenes.append(examen)

    if not examenes:
        return {"examen": None, "total": 0, "candidatos": [], "sin_habilitar": []}

    examen = examenes[0]
    contexto = {
        "id_examen": examen.id_examen,
        "materia": examen.materia,
        "carrera": examen.carrera.nombre if examen.carrera else None,
    }

    # Postulantes con inscripción vigente en alguno de los exámenes de hoy
    postulantes = []
    vistos = set()
    for activo in examenes:
        filas = db.query(Postulante).join(
            Inscripcion, Inscripcion.id_postulante == Postulante.id_postulante
        ).filter(
            Inscripcion.id_gestion == activo.id_gestion,
            Inscripcion.id_carrera == activo.id_carrera,
            Inscripcion.estado == "HABILITADO"
        ).all()
        for postulante in filas:
            if postulante.id_postulante in vistos:
                continue
            vistos.add(postulante.id_postulante)
            postulantes.append(postulante)

    candidatos = []
    sin_habilitar = []
    for postulante in postulantes:
        nombre = f"{postulante.nombres} {postulante.apellidos}"
        huellas = db.query(Huella).filter(
            Huella.id_postulante == postulante.id_postulante
        ).all()
        habilitadas = [
            h for h in huellas if h.habilitada and h.plantilla_biometrica
        ]
        for huella in habilitadas:
            if len(candidatos) >= limite:
                break
            candidatos.append({
                "indice": len(candidatos),
                "id_huella": huella.id_huella,
                "id_postulante": postulante.id_postulante,
                "ci": postulante.ci,
                "nombre_completo": nombre,
                "tipo_dedo": huella.tipo_dedo,
                "plantilla_b64": base64.b64encode(
                    huella.plantilla_biometrica
                ).decode("ascii"),
            })
        if huellas and not habilitadas:
            sin_habilitar.append({
                "id_postulante": postulante.id_postulante,
                "ci": postulante.ci,
                "nombre_completo": nombre,
                "dedos_registrados": sorted(h.tipo_dedo for h in huellas),
            })

    return {
        "examen": contexto,
        "total": len(candidatos),
        "candidatos": candidatos,
        "sin_habilitar": sin_habilitar,
    }


@router.post("/verificar-huella", response_model=MarcacionRespuestaOut)
@marking_router.post("/verificar-huella", response_model=MarcacionRespuestaOut)
async def verificar_huella_1a1(
    id_examen: int = Form(...),
    id_postulante: int = Form(...),
    tipo_dedo: int = Form(...),
    file: UploadFile = File(...),
    score_cliente: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    _: None = Depends(require_app_key)
):
    if not 1 <= tipo_dedo <= 10:
        raise HTTPException(status_code=422, detail="tipo_dedo debe estar entre 1 y 10")
    postulante = db.query(Postulante).filter(Postulante.id_postulante == id_postulante).first()
    if not postulante:
        raise HTTPException(status_code=404, detail="Postulante no encontrado")
    captura = await file.read()
    # Si el cliente ya comparó la huella con la ZKFinger SDK (la tiene instalada
    # junto al lector), confiamos en su score; si no, comparamos en el servidor.
    if score_cliente is not None and score_cliente >= UMBRAL_HUELLA_CLIENTE:
        coincide, score = True, float(score_cliente)
    else:
        coincide, score = fingerprint_service.verificar_huella_1a1(
            captura, id_postulante, tipo_dedo, db
        )
    if not coincide:
        return MarcacionRespuestaOut(
            resultado=ResultadoMarcacion.RECHAZADO,
            metodo=MetodoMarcacion.HUELLA,
            id_postulante=id_postulante,
            ci=postulante.ci,
            nombre_completo=f"{postulante.nombres} {postulante.apellidos}",
            mensaje="La huella no coincide con el dedo habilitado del postulante",
            score_similitud=score,
            fecha_hora=datetime.now()
        )
    return validar_cuatro_reglas_y_registrar(
        db, id_examen, postulante, MetodoMarcacion.HUELLA, score
    )


@router.post("/verificar-rostro", response_model=MarcacionRespuestaOut)
@marking_router.post("/verificar-rostro", response_model=MarcacionRespuestaOut)
async def verificar_rostro_1a1(
    id_examen: int = Form(...),
    id_postulante: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_app_key)
):
    postulante = db.query(Postulante).filter(Postulante.id_postulante == id_postulante).first()
    if not postulante:
        raise HTTPException(status_code=404, detail="Postulante no encontrado")
    rostro = db.query(Rostro).filter(
        Rostro.id_postulante == id_postulante,
        Rostro.habilitada.is_(True)
    ).first()
    if not rostro:
        return MarcacionRespuestaOut(
            resultado=ResultadoMarcacion.RECHAZADO,
            metodo=MetodoMarcacion.ROSTRO,
            id_postulante=id_postulante,
            ci=postulante.ci,
            nombre_completo=f"{postulante.nombres} {postulante.apellidos}",
            mensaje="El registro facial no está habilitado para este postulante",
            fecha_hora=datetime.now()
        )
    contenido = await file.read()
    imagen = face_service.procesar_imagen_bytes(contenido)
    embedding, _ = face_service.extraer_embedding(imagen) if imagen is not None else (None, None)
    score = face_service.similitud_coseno(embedding, rostro.embedding) if embedding else 0.0
    if score < 0.50:
        return MarcacionRespuestaOut(
            resultado=ResultadoMarcacion.RECHAZADO,
            metodo=MetodoMarcacion.ROSTRO,
            id_postulante=id_postulante,
            ci=postulante.ci,
            nombre_completo=f"{postulante.nombres} {postulante.apellidos}",
            mensaje="El rostro no coincide con el registro habilitado",
            score_similitud=round(score, 4),
            fecha_hora=datetime.now()
        )
    return validar_cuatro_reglas_y_registrar(
        db, id_examen, postulante, MetodoMarcacion.ROSTRO, round(score, 4)
    )


def _buscar_contexto_examen(
    db: Session,
    postulante: Postulante,
    id_examen: Optional[int] = None,
):
    """Busca un examen donde el postulante tenga inscripción vigente.

    Prioriza el examen indicado y luego revisa los exámenes activos de hoy.
    La asignación de aula/asiento es opcional.
    """
    ahora = datetime.now()

    def _en_ventana(examen: Examen) -> bool:
        inicio = datetime.combine(examen.fecha, examen.hora_inicio) - timedelta(minutes=45)
        fin = datetime.combine(examen.fecha, examen.hora_fin) + timedelta(
            minutes=examen.tolerancia_minutos or 0
        )
        return inicio <= ahora <= fin

    examenes = []
    if id_examen:
        elegido = db.query(Examen).filter(Examen.id_examen == id_examen).first()
        if elegido:
            examenes.append(elegido)
    # Primero los exámenes de hoy que estén dentro de su ventana horaria
    for activo in db.query(Examen).filter(Examen.fecha == ahora.date()).all():
        if _en_ventana(activo) and all(activo.id_examen != e.id_examen for e in examenes):
            examenes.append(activo)
    # Luego el resto de exámenes de hoy
    for activo in db.query(Examen).filter(Examen.fecha == ahora.date()).all():
        if all(activo.id_examen != e.id_examen for e in examenes):
            examenes.append(activo)

    for examen in examenes:
        inscripcion = db.query(Inscripcion).filter(
            Inscripcion.id_postulante == postulante.id_postulante,
            Inscripcion.id_gestion == examen.id_gestion,
            Inscripcion.id_carrera == examen.id_carrera,
            Inscripcion.estado == "HABILITADO",
        ).first()
        if not inscripcion:
            continue
        asignacion = db.query(Asignacion).filter(
            Asignacion.id_inscripcion == inscripcion.id_inscripcion,
            Asignacion.id_examen == examen.id_examen,
        ).first()
        return examen, inscripcion, asignacion
    return None, None, None


@router.post("/identificar-rostro")
@marking_router.post("/identificar-rostro")
async def identificar_rostro_automatico(
    file: UploadFile = File(...),
    id_examen: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    _: None = Depends(require_app_key)
):
    """Reconocimiento facial 1:N para estaciones de acceso.

    Detecta el rostro, lo compara contra todos los rostros habilitados y,
    si coincide, valida las reglas de acceso, registra el ingreso y devuelve
    los datos completos del postulante (carrera, materia, aula, asiento, hora).
    """
    contenido = await file.read()
    imagen = face_service.procesar_imagen_bytes(contenido)
    if imagen is None:
        return {"coincidencia": False, "mensaje": "Formato de imagen inválido"}

    embedding, _ = face_service.extraer_embedding(imagen)
    if embedding is None:
        return {"coincidencia": False, "mensaje": "No se detectó ningún rostro en la imagen"}

    rostros_activos = db.query(Rostro).filter(Rostro.habilitada.is_(True)).all()
    if not rostros_activos:
        return {"coincidencia": False, "mensaje": "No hay rostros habilitados en el sistema"}

    mejor_rostro = None
    mejor_score = -1.0
    for rostro in rostros_activos:
        similitud = face_service.similitud_coseno(embedding, rostro.embedding)
        if similitud > mejor_score:
            mejor_score = similitud
            mejor_rostro = rostro

    ahora = datetime.now()
    if mejor_rostro is None or mejor_score < 0.50:
        return {
            "coincidencia": False,
            "score_similitud": round(mejor_score, 4),
            "mensaje": "Rostro no reconocido",
        }

    postulante = db.query(Postulante).filter(
        Postulante.id_postulante == mejor_rostro.id_postulante
    ).first()
    if not postulante:
        return {"coincidencia": False, "mensaje": "Postulante no encontrado"}

    examen, inscripcion, asignacion = _buscar_contexto_examen(db, postulante, id_examen)

    nombre_completo = f"{postulante.nombres} {postulante.apellidos}"
    respuesta = {
        "coincidencia": True,
        "id_postulante": postulante.id_postulante,
        "ci": postulante.ci,
        "nombre_completo": nombre_completo,
        "score_similitud": round(mejor_score, 4),
        "fecha_hora": ahora.isoformat(),
        "hora_ingreso": ahora.strftime("%H:%M:%S"),
    }

    if not examen:
        respuesta.update({
            "resultado": "RECHAZADO",
            "mensaje": "El postulante no tiene una inscripción vigente para un examen de hoy",
        })
        return respuesta

    respuesta.update({
        "id_examen": examen.id_examen,
        "materia": examen.materia,
        "carrera": inscripcion.carrera.nombre if inscripcion.carrera else None,
        "aula": asignacion.aula.nombre if asignacion and asignacion.aula else "Sin asignar",
        "numero_asiento": asignacion.asiento.numero_asiento if asignacion and asignacion.asiento else None,
    })

    # Evitar duplicar el registro si el mismo postulante se detecta de nuevo
    # pocos segundos después (p. ej. permanece frente a la cámara).
    reciente = db.query(RegistroIngreso).filter(
        RegistroIngreso.id_examen == examen.id_examen,
        RegistroIngreso.id_inscripcion == inscripcion.id_inscripcion,
        RegistroIngreso.resultado == ResultadoMarcacion.ACEPTADO,
    ).order_by(RegistroIngreso.fecha_hora.desc()).first()

    if reciente and (ahora - reciente.fecha_hora) < timedelta(seconds=45):
        respuesta.update({
            "resultado": "ACEPTADO",
            "hora_ingreso": reciente.fecha_hora.strftime("%H:%M:%S"),
            "mensaje": f"Ingreso ya registrado a las {reciente.fecha_hora.strftime('%H:%M:%S')}",
        })
        return respuesta

    resultado = validar_cuatro_reglas_y_registrar(
        db, examen.id_examen, postulante, MetodoMarcacion.ROSTRO, round(mejor_score, 4)
    )
    respuesta.update({
        "resultado": (
            resultado.resultado.value
            if hasattr(resultado.resultado, "value")
            else str(resultado.resultado)
        ),
        "mensaje": resultado.mensaje,
        "aula": resultado.aula or respuesta.get("aula"),
        "numero_asiento": resultado.numero_asiento or respuesta.get("numero_asiento"),
    })
    return respuesta

# Contador en Tiempo Real
@router.get("/examen/{id_examen}/contador", response_model=ContadorTiempoRealOut)
def obtener_contador_tiempo_real(
    id_examen: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_app_key)
):
    examen = db.query(Examen).filter(Examen.id_examen == id_examen).first()
    if not examen:
        raise HTTPException(status_code=404, detail="Examen no encontrado")

    # Total de postulantes con inscripción habilitada para la carrera/gestión del examen
    total_asignados = db.query(func.count(Inscripcion.id_inscripcion)).filter(
        Inscripcion.id_gestion == examen.id_gestion,
        Inscripcion.id_carrera == examen.id_carrera,
        Inscripcion.estado == "HABILITADO"
    ).scalar() or 0

    # Total con al menos un ingreso ACEPTADO
    total_ingresados = db.query(func.count(distinct(RegistroIngreso.id_inscripcion))).filter(
        RegistroIngreso.id_examen == examen.id_examen,
        RegistroIngreso.resultado == ResultadoMarcacion.ACEPTADO
    ).scalar() or 0

    total_pendientes = max(0, total_asignados - total_ingresados)
    porcentaje = round((total_ingresados / total_asignados * 100), 2) if total_asignados > 0 else 0.0

    return ContadorTiempoRealOut(
        id_examen=examen.id_examen,
        materia=examen.materia,
        carrera=examen.carrera.nombre,
        fecha=examen.fecha,
        hora_inicio=examen.hora_inicio,
        hora_fin=examen.hora_fin,
        total_asignados=total_asignados,
        total_ingresados=total_ingresados,
        total_pendientes=total_pendientes,
        porcentaje_asistencia=porcentaje
    )
