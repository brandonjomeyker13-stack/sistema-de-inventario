"""
app/api/v1/auth.py — Endpoints de "cómo entro": registro, login, refresh,
verificación de correo y logout.

registro, login, refresh y verificar son públicos (no requieren
Depends(obtener_usuario_actual)); logout recibe el refresh_token en el
body, no requiere el access_token porque puede llamarse aunque el access
token ya haya expirado.
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core import limites
from app.database.session import get_db
from app.api.deps import obtener_usuario_actual
from app.models.usuario import Usuario
from app.schemas.auth import (
    UsuarioRegistro, UsuarioLogin, Token, RefrescarToken, GoogleLogin, TokenGoogle,
    DefinirPassword, ReenviarVerificacion, RecuperarPassword, RestablecerPassword,
)
from app.schemas.usuario import UsuarioOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/registro", response_model=UsuarioOut, status_code=201)
def registro(datos: UsuarioRegistro, request: Request, db: Session = Depends(get_db)):
    # Cada registro manda un correo, y el plan gratuito de Resend tiene un
    # cupo diario. Sin tope, un script podría gastarlo entero en un minuto
    # y dejar sin correo de verificación a los clientes de verdad.
    limites.exigir(
        f"registro:{limites.ip_del_cliente(request)}", maximo=5, segundos=3600,
        mensaje="Demasiadas cuentas creadas desde aquí. Intenta más tarde.",
    )
    return auth_service.registrar(db, datos.email, datos.password, datos.nombre_negocio)


@router.get("/verificar/{token}")
def verificar_email(token: str, db: Session = Depends(get_db)):
    auth_service.verificar_email(db, token)
    return {"detalle": "Correo verificado correctamente"}


@router.post("/login", response_model=Token)
def login(datos: UsuarioLogin, request: Request, db: Session = Depends(get_db)):
    ip = limites.ip_del_cliente(request)
    clave_cuenta = f"login:cuenta:{datos.email.lower().strip()}"

    # Dos límites, y hacen falta los dos:
    #
    #   - Por CUENTA, para que nadie pruebe contraseñas contra un correo
    #     concreto, aunque cambie de IP en cada intento.
    #   - Por IP, para que nadie recorra muchos correos distintos desde el
    #     mismo sitio; el límite por cuenta no lo vería.
    #
    # El de IP es más holgado a propósito: en una tienda con varios
    # empleados o tras un router compartido, todos salen con la misma IP.
    limites.exigir(
        clave_cuenta, maximo=8, segundos=900,
        mensaje="Demasiados intentos con este correo. Espera unos minutos "
                "o restablece tu contraseña.",
    )
    limites.exigir(f"login:ip:{ip}", maximo=30, segundos=900)

    credenciales = auth_service.iniciar_sesion(
        db, datos.email, datos.password,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    # Entró bien: se le perdonan los intentos fallidos. Si no, quien se
    # equivoca tres veces antes de acertar arrastraría el castigo el resto
    # del día.
    limites.limpiar(clave_cuenta)
    return credenciales


@router.post("/refresh", response_model=Token)
def refresh(datos: RefrescarToken, db: Session = Depends(get_db)):
    return auth_service.refrescar(db, datos.refresh_token)


@router.post("/google", response_model=TokenGoogle)
def login_google(datos: GoogleLogin, request: Request, db: Session = Depends(get_db)):
    """Entra o crea la cuenta con Google.

    El `id_token` se verifica contra Google en el servidor. Si ya existe
    una cuenta con ese correo, se enlaza en vez de fallar.

    La respuesta trae `requiere_password` y `perfil_completo` para que el
    frontend sepa si debe pedir contraseña y datos del negocio después de
    entrar.
    """
    # Cada intento verifica el token contra Google. El límite es holgado
    # porque aquí no se adivina nada: sin un token firmado por Google no
    # se pasa. Es solo para que nadie use nuestra API como ariete contra
    # el servicio de Google con nuestra cuota.
    limites.exigir(f"google:{limites.ip_del_cliente(request)}", maximo=30, segundos=900)
    return auth_service.iniciar_sesion_google(
        db, datos.id_token, datos.nombre_negocio,
        ip=limites.ip_del_cliente(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/definir-password", status_code=status.HTTP_204_NO_CONTENT)
def definir_password(
    datos: DefinirPassword,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Pone contraseña a una cuenta creada con Google.

    Requiere sesión iniciada. Falla si la cuenta ya tiene contraseña: para
    cambiarla está PUT /usuarios/yo/password, que pide la actual.
    """
    auth_service.definir_password(db, usuario_actual.id, datos.password)


@router.post("/reenviar-verificacion", status_code=status.HTTP_202_ACCEPTED)
def reenviar_verificacion(
    datos: ReenviarVerificacion, request: Request, db: Session = Depends(get_db),
):
    """Manda otra vez el correo de verificación.

    Responde 202 siempre, exista o no la cuenta: si contestara distinto,
    sería una forma cómoda de averiguar qué correos están registrados.
    """
    _limitar_envio_de_correo(request, datos.email, "reenvio")
    auth_service.reenviar_verificacion(db, datos.email)
    return {"detalle": "Si el correo está registrado y sin verificar, recibirás el enlace"}


@router.post("/recuperar-password", status_code=status.HTTP_202_ACCEPTED)
def recuperar_password(
    datos: RecuperarPassword, request: Request, db: Session = Depends(get_db),
):
    """Manda el enlace para restablecer la contraseña.

    Responde 202 siempre, exista o no la cuenta: si contestara distinto,
    sería una forma cómoda de averiguar qué correos están registrados.
    """
    _limitar_envio_de_correo(request, datos.email, "recuperacion")
    auth_service.recuperar_password(db, datos.email)
    return {"detalle": "Si ese correo tiene cuenta, te llegará el enlace en unos minutos"}


def _limitar_envio_de_correo(request: Request, email: str, accion: str) -> None:
    """Freno común a los dos endpoints que mandan un correo sin sesión.

    Sin esto, cualquiera puede pedir cien veces el enlace de recuperación
    del correo de otra persona y llenarle la bandeja. Es acoso barato, y
    además gasta el cupo diario del plan gratuito de Resend, que es el que
    necesitan los clientes de verdad.

    El límite por dirección es estricto y el de IP más ancho, igual que en
    el login. Se cuenta el intento aunque la cuenta no exista: si solo se
    contara cuando existe, la diferencia de comportamiento delataría qué
    correos están registrados — justo lo que el 202 constante evita.
    """
    limites.exigir(
        f"{accion}:email:{email.lower().strip()}", maximo=3, segundos=3600,
        mensaje="Ya se enviaron varios correos a esa dirección. Revisa tu "
                "bandeja (y la carpeta de spam) antes de pedir otro.",
    )
    limites.exigir(f"{accion}:ip:{limites.ip_del_cliente(request)}", maximo=10, segundos=3600)


@router.post("/restablecer-password", status_code=status.HTTP_204_NO_CONTENT)
def restablecer_password(
    datos: RestablecerPassword, request: Request, db: Session = Depends(get_db),
):
    """Cambia la contraseña con el token del correo.

    Cierra todas las sesiones abiertas del usuario: si alguien había
    entrado a la cuenta, este es el momento en que se le echa.
    """
    # El token son 43 caracteres aleatorios: adivinarlo a fuerza bruta no
    # es realista. El límite está para que nadie lo intente igualmente y
    # de paso nos haga miles de consultas a la base.
    limites.exigir(f"restablecer:{limites.ip_del_cliente(request)}", maximo=10, segundos=900)
    auth_service.restablecer_password(db, datos.token, datos.password)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(datos: RefrescarToken, db: Session = Depends(get_db)):
    auth_service.cerrar_sesion(db, datos.refresh_token)