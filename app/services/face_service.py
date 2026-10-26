import logging
import os
import threading
import time

import cv2
import numpy as np

log = logging.getLogger(__name__)

# ── Ajustes de rendimiento (se pueden cambiar con variables de entorno) ──
# Tamaño de detección: más chico = más rápido. 480 va bien para un rostro
# frente a la cámara; usa 640 si los rostros salen pequeños o lejos.
DET_SIZE = int(os.getenv("FACE_DET_SIZE", "480"))
# Las fotos más grandes que esto (lado mayor, en px) se reducen antes de analizarlas.
MAX_LADO_IMAGEN = int(os.getenv("FACE_MAX_IMAGE_SIDE", "800"))
# Cuántas fotos se analizan a la vez. Más hilos no aceleran: se pelean por la CPU.
MAX_INFERENCIAS_SIMULTANEAS = int(os.getenv("FACE_MAX_CONCURRENT", "2"))
# Cada cuántos segundos como máximo se revisa en la BD si cambiaron los rostros habilitados.
REVISION_CACHE_S = float(os.getenv("FACE_CACHE_CHECK_SECONDS", "2"))


class FaceService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            inst = super(FaceService, cls).__new__(cls)
            inst.app = None
            inst._app_lock = threading.Lock()
            inst._semaforo = threading.BoundedSemaphore(MAX_INFERENCIAS_SIMULTANEAS)
            inst._cache_lock = threading.Lock()
            # (firma, matriz de embeddings, ids de rostro, ids de postulante)
            inst._cache = None
            inst._ultima_revision = 0.0
            cls._instance = inst
        return cls._instance

    # ───────────────────────── modelo ─────────────────────────
    def _get_app(self):
        if self.app is None:
            with self._app_lock:
                if self.app is None:
                    try:
                        from insightface.app import FaceAnalysis
                    except ModuleNotFoundError as error:
                        raise RuntimeError(
                            "La funcionalidad facial requiere instalar insightface y sus "
                            "dependencias nativas."
                        ) from error

                    # buffalo_s (detector scrfd + extractor arcface 512d).
                    # Solo se cargan detección y reconocimiento: los modelos de
                    # landmarks, edad y género no se usan y gastan CPU en cada foto.
                    # Los embeddings son los mismos: los rostros ya registrados siguen válidos.
                    app = FaceAnalysis(
                        name="buffalo_s",
                        providers=["CPUExecutionProvider"],
                        allowed_modules=["detection", "recognition"],
                    )
                    app.prepare(ctx_id=0, det_size=(DET_SIZE, DET_SIZE))
                    self.app = app
        return self.app

    def procesar_imagen_bytes(self, image_bytes: bytes):
        """Convierte bytes crudos a matriz BGR para OpenCV (reduce fotos enormes)."""
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        alto, ancho = img.shape[:2]
        lado = max(alto, ancho)
        if lado > MAX_LADO_IMAGEN:
            escala = MAX_LADO_IMAGEN / float(lado)
            img = cv2.resize(
                img, (int(ancho * escala), int(alto * escala)), interpolation=cv2.INTER_AREA
            )
        return img

    def extraer_embedding(self, img_bgr):
        """Detecta rostros y extrae el embedding del rostro dominante (más grande)"""
        app = self._get_app()
        # El semáforo evita que 15 fotos a la vez saturen la CPU y todas se vuelvan lentas.
        with self._semaforo:
            faces = app.get(img_bgr)
        if not faces:
            return None, None

        # Si hay más de un rostro, tomar el de mayor área delimitada (bbox)
        face_principal = max(
            faces,
            key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
        )

        # El embedding viene normalizado en norma L2
        normed_embedding = face_principal.normed_embedding.tolist()
        return normed_embedding, face_principal.bbox

    @staticmethod
    def similitud_coseno(emb1: list, emb2: list) -> float:
        """Calcula el producto punto (similitud coseno) entre embeddings normalizados"""
        a = np.array(emb1, dtype=np.float32)
        b = np.array(emb2, dtype=np.float32)
        return float(np.dot(a, b))

    # ───────────── caché en memoria de los rostros habilitados ─────────────
    @staticmethod
    def _firma_bd(db):
        """Consulta barata: cambia cuando se habilita, deshabilita o registra un rostro."""
        from sqlalchemy import func
        from app.models.biometria import Rostro

        fila = db.query(
            func.count(Rostro.id_rostro),
            func.coalesce(func.sum(Rostro.id_rostro), 0),
            func.coalesce(func.max(Rostro.id_rostro), 0),
        ).filter(Rostro.habilitada.is_(True)).one()
        return tuple(int(x or 0) for x in fila)

    @staticmethod
    def _leer_rostros(db):
        """Lee solo lo necesario (sin la foto JPG de cada rostro)."""
        from app.models.biometria import Rostro

        return db.query(
            Rostro.id_rostro, Rostro.id_postulante, Rostro.embedding
        ).filter(Rostro.habilitada.is_(True)).all()

    def invalidar_cache(self):
        """Se llama cuando cambian los rostros: la próxima búsqueda recarga desde la BD."""
        with self._cache_lock:
            self._cache = None
            self._ultima_revision = 0.0

    def refrescar_cache(self, db, forzar=False):
        ahora = time.monotonic()
        if (not forzar and self._cache is not None
                and ahora - self._ultima_revision < REVISION_CACHE_S):
            return
        with self._cache_lock:
            ahora = time.monotonic()
            if (not forzar and self._cache is not None
                    and ahora - self._ultima_revision < REVISION_CACHE_S):
                return
            firma = self._firma_bd(db)
            self._ultima_revision = time.monotonic()
            if not forzar and self._cache is not None and self._cache[0] == firma:
                return
            filas = self._leer_rostros(db)
            if filas:
                matriz = np.asarray([f[2] for f in filas], dtype=np.float32)
            else:
                matriz = np.zeros((0, 512), dtype=np.float32)
            self._cache = (
                firma,
                matriz,
                [f[0] for f in filas],
                [f[1] for f in filas],
            )
            log.info("Caché facial recargada: %d rostros habilitados", len(filas))

    def buscar_mejor(self, embedding, db):
        """Búsqueda 1:N con un solo producto matricial.

        Devuelve (id_rostro, id_postulante, score) del rostro más parecido,
        o None si no hay rostros habilitados.
        """
        self.refrescar_cache(db)
        cache = self._cache
        if cache is None:
            return None
        _, matriz, ids_rostro, ids_postulante = cache
        if matriz.shape[0] == 0:
            return None
        consulta = np.asarray(embedding, dtype=np.float32)
        puntajes = matriz @ consulta
        i = int(np.argmax(puntajes))
        return ids_rostro[i], ids_postulante[i], float(puntajes[i])

    def precalentar(self, db):
        """Carga el modelo y la caché al arrancar, para que la 1.ª foto no espere."""
        self._get_app()
        self.refrescar_cache(db, forzar=True)


face_service = FaceService()