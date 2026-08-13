"""
app/core/limites.py — Límite de intentos por ventana de tiempo.

Hasta ahora no había ninguno: treinta contraseñas erróneas seguidas se
procesaban igual que la primera, y el endpoint del asistente —que cuesta
dinero en cada llamada— se podía disparar en bucle con una sola cuenta.

Se guarda en memoria del proceso, no en la base. Es una decisión
consciente para este tamaño de proyecto:

  - En Render corre UNA instancia, así que la memoria del proceso ES el
    estado global. Con varias instancias esto contaría por separado en
    cada una y habría que mover el contador a Postgres o Redis.
  - Un contador en base de datos significaría un INSERT por cada intento
    fallido, incluidos los de un ataque — o sea, ayudar a saturar justo
    lo que se quiere proteger.
  - Al reiniciarse el servicio los contadores se pierden. En Render free,
    que se duerme a los 15 minutos, eso pasa a diario. Es aceptable:
    esto está para frenar el goteo de un script, no para aguantar un
    ataque coordinado.

Si algún día hay varias instancias, lo que cambia es la implementación de
`_registrar`; las llamadas desde las rutas se quedan igual.
"""

import threading
import time

from fastapi import Request

# Cuántas claves distintas se guardan como mucho. Sin este tope, un
# atacante que rote la IP en cada intento haría crecer el diccionario sin
# fin hasta tumbar el proceso por memoria — el propio antídoto sería el
# veneno.
MAX_CLAVES = 10_000


class DemasiadosIntentos(Exception):
    """Se superó el límite de intentos. Se traduce a HTTP 429.

    Lleva `segundos` para poder mandar la cabecera Retry-After: el
    frontend puede decir "espera 2 minutos" en vez de un error opaco que
    invita a seguir pulsando.
    """

    def __init__(self, mensaje: str, segundos: int):
        super().__init__(mensaje)
        self.segundos = segundos


_eventos: dict[str, list[float]] = {}
# Uvicorn atiende peticiones en varios hilos (las rutas son `def`, no
# `async def`, así que FastAPI las manda al threadpool). Sin el candado,
# dos peticiones simultáneas pueden leer la misma lista a la vez y perder
# un intento — justo lo que un atacante necesita.
_candado = threading.Lock()


def _podar(ahora: float) -> None:
    """Tira las claves sin eventos vivos. Se llama solo cuando hace falta."""
    muertas = [k for k, v in _eventos.items() if not v or v[-1] < ahora - 3600]
    for k in muertas:
        del _eventos[k]


def exigir(clave: str, maximo: int, segundos: int, mensaje: str | None = None) -> None:
    """Cuenta un intento y lanza DemasiadosIntentos si se pasó del límite.

    Ventana deslizante: se guardan las marcas de tiempo de los intentos
    recientes y se descartan las que ya salieron de la ventana. Es más
    justo que reiniciar el contador cada N minutos, donde alguien puede
    gastar el doble de intentos a caballo entre dos ventanas.
    """
    ahora = time.time()
    with _candado:
        if len(_eventos) > MAX_CLAVES:
            _podar(ahora)

        recientes = [t for t in _eventos.get(clave, []) if t > ahora - segundos]

        if len(recientes) >= maximo:
            # El intento bloqueado NO se apunta. Si se apuntara, seguir
            # insistiendo alargaría el castigo indefinidamente y una
            # persona real que se equivocó nunca podría volver a entrar.
            espera = int(recientes[0] + segundos - ahora) + 1
            _eventos[clave] = recientes
            raise DemasiadosIntentos(
                mensaje or f"Demasiados intentos. Espera {espera} segundos.",
                espera,
            )

        recientes.append(ahora)
        _eventos[clave] = recientes


def limpiar(clave: str) -> None:
    """Borra el contador de una clave.

    Se llama tras un login correcto: quien acaba de demostrar que la
    cuenta es suya no debe quedar castigado por haberse equivocado tres
    veces antes de acertar.
    """
    with _candado:
        _eventos.pop(clave, None)


def ip_del_cliente(request: Request) -> str:
    """La IP de quien llama, no la del proxy.

    Render (como Cloudflare o cualquier otro balanceador) recibe la
    petición y la reenvía a la aplicación. Visto desde uvicorn,
    `request.client.host` es entonces la IP del proxy: la MISMA para todo
    el mundo. Un límite por esa clave castigaría a todos los tenderos a la
    vez en cuanto alguien insistiera.

    La IP real va en X-Forwarded-For, y la primera de la lista es la del
    cliente original.

    Advertencia: esa cabecera la puede falsificar quien llame directamente
    a la API sin pasar por el proxy. Para un límite de intentos es un
    riesgo aceptable —lo peor que consigue es saltarse su propio castigo,
    no el de otro—, pero NO sirve para decidir permisos.
    """
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"
