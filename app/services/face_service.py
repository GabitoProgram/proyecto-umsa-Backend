import cv2
import numpy as np
import insightface
from insightface.app import FaceAnalysis

class FaceService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FaceService, cls).__new__(cls)
            # Inicializar modelo buffalo_s (detector scrfd + extractor arcface 512d)
            cls._instance.app = FaceAnalysis(name="buffalo_s", providers=['CPUExecutionProvider'])
            cls._instance.app.prepare(ctx_id=0, det_size=(640, 640))
        return cls._instance

    def procesar_imagen_bytes(self, image_bytes: bytes):
        """Convierte bytes crudos a matriz BGR para OpenCV"""
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img

    def extraer_embedding(self, img_bgr):
        """Detecta rostros y extrae el embedding del rostro dominante (más grande)"""
        faces = self.app.get(img_bgr)
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

face_service = FaceService()
