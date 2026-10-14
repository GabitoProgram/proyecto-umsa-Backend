"""Lectura de archivos con listados de postulantes.

Acepta Excel (``.xlsx``/``.xls``) y CSV, que es como se descargan la mayoría
de los sistemas. El archivo real que entrega la institución no tiene
encabezados estables: llevan acentos, mayúsculas, espacios y hasta errores de
tipeo («patemo» en lugar de «paterno», «dieccion» en lugar de «direccion»).
Por eso los nombres de columna se normalizan (sin acentos, en minúsculas, sin
espacios) y luego se comparan contra un diccionario de alias; si no hay
coincidencia exacta se recurre a una aproximada.

Una fila del archivo equivale a una inscripción: el mismo CI puede aparecer
dos veces si el postulante se inscribió en dos carreras. La carrera de cada
fila sale de la columna «programa».
"""

import io
import unicodedata
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

import pandas as pd

# Archivos de texto separado, que son como se descargan muchos sistemas.
_EXTENSIONES_CSV = (".csv", ".txt", ".tsv")

# Columna del Excel (normalizada) -> campo interno. Las claves van sin
# acentos, sin espacios y en minúsculas, igual que `normalizar()`.
ALIAS = {
    # documento de identidad (en el Excel esta columna se llama «dip»)
    "ci": "ci", "dip": "ci", "dni": "ci", "cedula": "ci",
    "documento": "ci", "documentoidentidad": "ci", "numerodocumento": "ci",
    # nombres y apellidos
    "nombres": "nombres", "nombre": "nombres", "nombrescompletos": "nombres",
    "apellidosynombres": "nombres",
    "paterno": "paterno", "apellidopaterno": "paterno", "apellidos": "paterno",
    "materno": "materno", "apellidomaterno": "materno",
    # datos personales
    "genero": "genero", "sexo": "genero",
    "fechanacimiento": "fecha_nacimiento", "fechnacimiento": "fecha_nacimiento",
    "fechanac": "fecha_nacimiento", "nacimiento": "fecha_nacimiento",
    "telefono": "telefono", "celular": "telefono", "fono": "telefono",
    "telefonocontacto": "telefono",
    "correo": "correo", "email": "correo", "mail": "correo",
    "correoelectronico": "correo", "correoe": "correo",
    "direccion": "direccion", "domicilio": "direccion",
    "direcciondomiciliaria": "direccion",
    # carrera del postulante, una por fila
    "programa": "programa", "carrera": "programa", "carreraprofesional": "programa",
    "programaestudio": "programa", "programadeestudio": "programa",
}

# Un encabezado que no está en ALIAS todavía puede corresponderse con uno si
# está cerca. 0.75 alcanza para «patemo»~«paterno» (0.77) y «dieccion»~«direccion»
# (0.82), y queda por debajo de vecinos peligrosos como «colegio»~«correo» (0.46).
UMBRAL_APROXIMADO = 0.75

_MASCULINO = {"m", "masc", "masculino", "varon", "hombre", "mbre"}
_FEMENINO = {"f", "fem", "femenino", "mujer"}


def normalizar(texto) -> str:
    """«Fec. Nacimiento» -> «fechnacimiento»."""
    if texto is None:
        return ""
    salida = str(texto).strip().lower()
    salida = unicodedata.normalize("NFKD", salida)
    salida = "".join(c for c in salida if not unicodedata.combining(c))
    return "".join(c for c in salida if c.isalnum())


def _mejor_candidato(clave: str, ocupados: set):
    """Columna parecida a alguna conocida, descartando campos ya tomados."""
    mejor, mejor_ratio = None, 0.0
    for alias, campo in ALIAS.items():
        if campo in ocupados:
            continue
        ratio = SequenceMatcher(None, clave, alias).ratio()
        if ratio > mejor_ratio:
            mejor, mejor_ratio = campo, ratio
    return mejor if mejor_ratio >= UMBRAL_APROXIMADO else None


def detectar_columnas(columnas) -> dict:
    """Mapea cada columna del Excel a su campo interno.

    Devuelve ``{nombre_de_columna_del_excel: campo}``. Un campo sólo puede ser
    reclamado una vez: si el archivo trae «ci» y «dip», gana la primera.
    """
    asignacion = {}
    ocupados = set()
    for columna in columnas:
        clave = normalizar(columna)
        if not clave:
            continue
        campo = ALIAS.get(clave) or _mejor_candidato(clave, ocupados)
        if campo and campo not in ocupados:
            asignacion[columna] = campo
            ocupados.add(campo)
    return asignacion


def _como_texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float):
        if pd.isna(valor):
            return ""
        if valor.is_integer():
            return str(int(valor))
    if isinstance(valor, int):
        return str(valor)
    texto = str(valor).strip()
    return "" if texto.lower() in ("nan", "none", "nat", "null", "<na>") else texto


def _como_fecha(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = _como_texto(valor)
    if not texto:
        return None
    # número de serie de Excel (p. ej. 38422 = 2005-03-15)
    if texto.isdigit() and len(texto) <= 5:
        try:
            return (datetime(1899, 12, 30) + timedelta(days=int(texto))).date()
        except (OverflowError, ValueError):
            return None
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    try:
        momento = pd.to_datetime(texto, dayfirst=True, errors="raise")
    except (ValueError, TypeError, OverflowError):
        return None
    return None if momento is None or pd.isna(momento) else momento.date()


def _como_genero(valor):
    """La app guarda «MASCULINO»/«FEMENINO»; el Excel trae M, F o texto largo."""
    texto = _como_texto(valor)
    if not texto:
        return None
    limpio = normalizar(texto)
    if limpio in _MASCULINO:
        return "MASCULINO"
    if limpio in _FEMENINO:
        return "FEMENINO"
    return texto.upper()


def _leer_csv(contenido: bytes, encabezado):
    """Lee un CSV con el separador y la codificación que toquen.

    En español el separador habitual es «;» y el texto suele venir en
    latin-1 en vez de UTF-8, así que se prueban varias combinaciones.
    """
    ultimo_error = None
    for codificacion in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            texto = contenido.decode(codificacion)
        except UnicodeDecodeError as error:
            ultimo_error = error
            continue
        for separador in (None, ";", ",", "\t", "|"):
            try:
                return pd.read_csv(io.StringIO(texto), header=encabezado, dtype=object,
                                   sep=separador, engine="python")
            except Exception as error:  # noqa: BLE001 - se prueban los demás separadores
                ultimo_error = error
        # La codificación era válida: el problema no está ahí.
        break
    raise ValueError(f"No se pudo leer el CSV ({ultimo_error})")


def _leer_hoja(contenido: bytes, nombre: str, encabezado):
    """Primera hoja del Excel, o el CSV si el archivo lo es."""
    es_csv = nombre.lower().endswith(_EXTENSIONES_CSV)
    try:
        if es_csv:
            return _leer_csv(contenido, encabezado)
        return pd.read_excel(io.BytesIO(contenido), sheet_name=0, header=encabezado, dtype=object)
    except Exception:
        if es_csv:
            raise
        # Un .csv mal nombrado (o un Excel ilegible) se intenta como texto.
        return _leer_csv(contenido, encabezado)


def _leer_dataframe(contenido: bytes, nombre: str = ""):
    """Lee la primera hoja probando dos filas de encabezado.

    Algunos reportes traen un título fusionado por encima de la fila de
    encabezados; en ese caso se reintenta tomando la segunda fila.
    """
    alternativa = None
    for encabezado in (0, 1):
        try:
            df = _leer_hoja(contenido, nombre, encabezado)
        except Exception:  # noqa: BLE001 - cualquier fallo de lectura pasa a la siguiente fila
            continue
        columnas = detectar_columnas(list(df.columns))
        if len(columnas) < 3:
            continue
        # Ideal: el archivo trae documento y nombres bien identificados.
        if {"ci", "nombres"} <= set(columnas.values()):
            return df, columnas
        if alternativa is None:
            alternativa = (df, columnas)
    if alternativa:
        return alternativa
    raise ValueError("No se reconocieron los encabezados del archivo.")


def leer_postulantes(contenido: bytes, nombre_archivo: str = ""):
    """Devuelve ``(filas, columnas_detectadas)``.

    Acepta Excel (``.xlsx``/``.xls``) y CSV. Cada fila es un dict con
    ``ci``, ``nombres``, ``apellidos``, ``genero``, ``fecha_nacimiento``,
    ``telefono``, ``correo``, ``direccion`` y ``programa`` (la carrera, en
    texto tal como viene en el archivo).
    """
    df, columnas = _leer_dataframe(contenido, nombre_archivo)
    filas = []
    for _, fila in df.iterrows():
        datos = {}
        for columna, campo in columnas.items():
            valor = fila.get(columna)
            if campo == "fecha_nacimiento":
                datos[campo] = _como_fecha(valor)
            elif campo == "genero":
                datos[campo] = _como_genero(valor)
            else:
                datos[campo] = _como_texto(valor)
        # El Excel trae paterno y materno por separado; la app usa un solo campo.
        datos["apellidos"] = " ".join(
            parte for parte in (datos.get("paterno", ""), datos.get("materno", "")) if parte
        ).strip()
        if datos.get("ci") and datos.get("nombres"):
            filas.append(datos)
    return filas, columnas
