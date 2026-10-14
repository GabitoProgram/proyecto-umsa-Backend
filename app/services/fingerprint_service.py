from typing import Tuple
from sqlalchemy.orm import Session
from app.models.biometria import Huella

class FingerprintService:
    """
    Servicio de abstracción biométrica dactilar.
    
    NOTA DE INTEGRACIÓN HARDWARE:
    Actualmente opera en modo SIMULACIÓN (MOCK) para pruebas de desarrollo.
    Cuando se disponga del lector físico ZKTeco ZK4500, esta clase integrará
    la biblioteca `pyzkfp` sobre el SDK ZKFinger de Windows / libzkfp en Linux:
        - zkfp2.Init()
        - zkfp2.OpenDevice(0)
        - zkfp2.DBMatch(hDBCache, template1, template2)
    """

    @staticmethod
    def verificar_huella_1a1(
        template_bytes: bytes,
        id_postulante: int,
        tipo_dedo: int,
        db: Session
    ) -> Tuple[bool, float]:
        """Compara la captura únicamente con el dedo seleccionado del postulante."""
        huella = db.query(Huella).filter(
            Huella.id_postulante == id_postulante,
            Huella.tipo_dedo == tipo_dedo,
            Huella.habilitada.is_(True)
        ).first()
        if not huella or not template_bytes:
            return False, 0.0
        coincide = template_bytes == huella.plantilla_biometrica
        return coincide, 100.0 if coincide else 0.0

fingerprint_service = FingerprintService()
