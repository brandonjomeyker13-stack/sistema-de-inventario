"""
Qué puede PROPONER el asistente, y la validación de esa propuesta.

EL ASISTENTE PROPONE, NUNCA EJECUTA. Cuando detecta que le piden crear un
producto o registrar mercancía, devuelve una acción propuesta con su frase
de confirmación. Quien ejecuta es el frontend, llamando al endpoint normal,
y solo después de que el tendero diga que sí.

Esto no es exceso de celo: la entrada suele ser voz, y "cuatro mil" y
"catorce mil" suenan casi igual con una nevera de fondo. Un producto creado
con el precio mal se vende mal durante días sin que nadie lo note.
"""

from app.services.asistente_service.instrucciones import ACCIONES_PERMITIDAS


def validar(accion) -> dict | None:
    """Deja pasar solo acciones del catálogo cerrado y bien formadas.

    Un modelo puede devolver un tipo inventado o datos incompletos. Antes
    de que eso llegue al frontend —que lo va a mostrar como una propuesta
    con un botón de confirmar— hay que descartarlo aquí.
    """
    if not isinstance(accion, dict):
        return None
    if accion.get("tipo") not in ACCIONES_PERMITIDAS:
        return None
    if not isinstance(accion.get("datos"), dict):
        return None
    if not accion.get("confirmacion"):
        return None
    return {
        "tipo": accion["tipo"],
        "datos": accion["datos"],
        "confirmacion": str(accion["confirmacion"]),
    }
