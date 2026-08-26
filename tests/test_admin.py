"""
El panel de administración.

Es el ÚNICO sitio del proyecto que puede ver y tocar los datos de otros
negocios, así que la mitad de estas pruebas son sobre quién NO puede entrar.

En todo el resto del sistema la seguridad no depende de una comprobación:
depende de que cada consulta lleve `usuario_id` y no pueda alcanzar filas
ajenas. Aquí la única barrera es `exigir_admin`.
"""

import pytest
from fastapi import HTTPException

from app.api import deps
from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.core.fechas import hoy_local, sumar_dias
from app.models.registro_admin import RegistroAdmin
from app.services import admin_service, product_service, venta_service


@pytest.fixture
def admin(db, usuario):
    usuario.es_admin = True
    db.commit()
    return usuario


# --- Quién puede entrar ---------------------------------------------------

def test_un_usuario_normal_no_entra(db, usuario):
    assert usuario.es_admin is False
    with pytest.raises(HTTPException) as exc:
        deps.exigir_admin(usuario)
    assert exc.value.status_code == 403


def test_un_admin_si_entra(db, admin):
    assert deps.exigir_admin(admin) is admin


def test_un_admin_con_la_suscripcion_vencida_sigue_entrando(db, admin):
    """Tiene que poder entrar precisamente cuando hay que arreglar cuentas.
    Dejarnos fuera del panel por nuestra propia fecha de pago sería
    absurdo."""
    admin.suscripcion_hasta = sumar_dias(-30)
    admin.prueba_hasta = sumar_dias(-60)
    db.commit()

    assert deps.exigir_admin(admin) is admin


def test_es_admin_no_se_puede_poner_desde_ningun_schema_de_entrada():
    """El agujero que convertiría a cualquiera en administrador con una
    sola petición."""
    from app.schemas.auth import GoogleLogin, UsuarioRegistro
    from app.schemas.usuario import UsuarioActualizar

    for schema in (UsuarioRegistro, GoogleLogin, UsuarioActualizar):
        assert "es_admin" not in schema.model_fields, schema.__name__


def test_un_usuario_nuevo_no_nace_admin(db):
    from app.repositories import usuario_repository

    nuevo = usuario_repository.crear(db, "nuevo@tienda.com", "hash", "Tienda")
    assert nuevo.es_admin is False


# --- Lo que ve el panel ---------------------------------------------------

def test_lista_todos_los_negocios(db, admin, otro_usuario):
    lista = admin_service.listar_negocios(db)
    assert lista["total"] == 2
    assert {n["nombre_negocio"] for n in lista["negocios"]} == {
        "Tienda de prueba", "Otra tienda",
    }


def test_distingue_las_cuatro_situaciones(db, admin, otro_usuario):
    admin.suscripcion_hasta = sumar_dias(30)

    otro_usuario.suscripcion_hasta = None
    otro_usuario.prueba_hasta = sumar_dias(3)
    db.commit()

    por_id = {n["id"]: n for n in admin_service.listar_negocios(db)["negocios"]}
    assert por_id[admin.id]["situacion"] == "pagando"
    assert por_id[otro_usuario.id]["situacion"] == "prueba"

    otro_usuario.prueba_hasta = sumar_dias(-1)
    db.commit()
    por_id = {n["id"]: n for n in admin_service.listar_negocios(db)["negocios"]}
    assert por_id[otro_usuario.id]["situacion"] == "sin_pagar"

    otro_usuario.suscripcion_hasta = sumar_dias(-5)
    db.commit()
    por_id = {n["id"]: n for n in admin_service.listar_negocios(db)["negocios"]}
    assert por_id[otro_usuario.id]["situacion"] == "vencida"


def test_marca_a_quien_se_le_vence_esta_semana(db, admin, otro_usuario):
    """Es el número que se mira cada lunes: a quién hay que cobrarle."""
    admin.suscripcion_hasta = sumar_dias(3)      # se le acaba esta semana
    otro_usuario.suscripcion_hasta = sumar_dias(60)
    db.commit()

    lista = admin_service.listar_negocios(db)
    assert lista["por_vencer"] == 1
    por_id = {n["id"]: n for n in lista["negocios"]}
    assert por_id[admin.id]["por_vencer"] is True
    assert por_id[otro_usuario.id]["por_vencer"] is False


def test_muestra_si_la_cuenta_se_esta_usando(db, admin):
    """Un negocio con cero productos a los tres días es alguien a quien hay
    que llamar, no esperar a que se le acabe la prueba."""
    p = product_service.agregar(db, admin.id, "Arroz", 10, 2000, 1500)
    venta_service.vender(db, admin.id, [{"producto_id": p.id, "cantidad": 1}])

    negocio = admin_service.obtener_negocio(db, admin.id)
    assert negocio["productos"] == 1
    assert negocio["ventas_ultimos_dias"] == 1


def test_el_panel_NO_expone_las_ventas_del_cliente(db, admin, otro_usuario):
    """Los datos de una tienda son de esa tienda. Que nosotros mantengamos
    el sistema no nos da derecho a mirar qué vende."""
    p = product_service.agregar(db, otro_usuario.id, "Arroz", 10, 2000, 1500)
    venta_service.vender(db, otro_usuario.id, [{"producto_id": p.id, "cantidad": 3}])

    negocio = admin_service.obtener_negocio(db, otro_usuario.id)

    prohibido = {"ventas", "productos_detalle", "fiados", "total_vendido", "ganancia"}
    assert not (prohibido & set(negocio)), "el panel está exponiendo el negocio del cliente"
    # Solo el recuento, que no dice ni qué ni cuánto.
    assert negocio["ventas_ultimos_dias"] == 1


# --- Cambiar la suscripción ----------------------------------------------

def test_activar_una_suscripcion(db, admin, otro_usuario):
    hasta = sumar_dias(30)
    admin_service.cambiar_suscripcion(db, admin, otro_usuario.id, hasta, "pagó por Nequi")

    db.refresh(otro_usuario)
    assert otro_usuario.suscripcion_hasta == hasta
    assert deps.estado_acceso(otro_usuario)["activa"] is True


def test_quitar_la_suscripcion_deja_la_cuenta_en_solo_lectura(db, admin, otro_usuario):
    otro_usuario.suscripcion_hasta = sumar_dias(30)
    otro_usuario.prueba_hasta = sumar_dias(-60)
    db.commit()

    admin_service.cambiar_suscripcion(db, admin, otro_usuario.id, None, "dejó de pagar")

    db.refresh(otro_usuario)
    assert otro_usuario.suscripcion_hasta is None
    assert deps.estado_acceso(otro_usuario)["activa"] is False
    # Y sigue pudiendo entrar: solo lectura no es bloqueo.
    assert otro_usuario.activo is True


def test_quitar_la_suscripcion_no_devuelve_los_dias_de_prueba(db, admin, otro_usuario):
    """La regla que sostiene todo el modelo de cobro."""
    otro_usuario.prueba_hasta = sumar_dias(-60)
    otro_usuario.suscripcion_hasta = sumar_dias(30)
    db.commit()

    admin_service.cambiar_suscripcion(db, admin, otro_usuario.id, None)

    db.refresh(otro_usuario)
    assert deps.estado_acceso(otro_usuario)["activa"] is False


def test_no_se_puede_poner_una_fecha_pasada(db, admin, otro_usuario):
    """Siempre es un dedazo, y el efecto —dejar al cliente sin vender— se
    nota al instante y sin explicación posible."""
    with pytest.raises(ErrorNegocio) as exc:
        admin_service.cambiar_suscripcion(db, admin, otro_usuario.id, sumar_dias(-1))
    assert "ya pasó" in str(exc.value)


def test_hoy_si_se_permite(db, admin, otro_usuario):
    """Vence al final del día, no al principio."""
    admin_service.cambiar_suscripcion(db, admin, otro_usuario.id, hoy_local())

    db.refresh(otro_usuario)
    assert deps.estado_acceso(otro_usuario)["activa"] is True


def test_una_fecha_mal_escrita_da_error_claro(db, admin, otro_usuario):
    with pytest.raises(ErrorNegocio) as exc:
        admin_service.cambiar_suscripcion(db, admin, otro_usuario.id, "30/12/2026")
    assert "AAAA-MM-DD" in str(exc.value)


def test_un_negocio_que_no_existe_da_404(db, admin):
    with pytest.raises(NoEncontrado):
        admin_service.cambiar_suscripcion(db, admin, "no-existe", sumar_dias(30))


# --- La bitácora ----------------------------------------------------------

def test_cada_cambio_queda_registrado(db, admin, otro_usuario):
    hasta = sumar_dias(30)
    admin_service.cambiar_suscripcion(db, admin, otro_usuario.id, hasta, "pagó por Nequi el 12")

    registro = db.query(RegistroAdmin).one()
    assert registro.admin_id == admin.id
    assert registro.usuario_id == otro_usuario.id
    assert registro.accion == "suscripcion"
    assert registro.valor_despues == hasta
    assert registro.nota == "pagó por Nequi el 12"


def test_guarda_el_valor_de_ANTES(db, admin, otro_usuario):
    """Con solo el valor nuevo, una fila dice "le puso hasta el 30" pero no
    si eso fue extenderle un mes o quitarle tres."""
    otro_usuario.suscripcion_hasta = sumar_dias(60)
    db.commit()

    admin_service.cambiar_suscripcion(db, admin, otro_usuario.id, sumar_dias(30))

    registro = db.query(RegistroAdmin).one()
    assert registro.valor_antes == sumar_dias(60)
    assert registro.valor_despues == sumar_dias(30)


def test_la_bitacora_va_de_lo_mas_reciente_hacia_atras(db, admin, otro_usuario):
    admin_service.cambiar_suscripcion(db, admin, otro_usuario.id, sumar_dias(10), "primero")
    admin_service.cambiar_suscripcion(db, admin, otro_usuario.id, sumar_dias(20), "segundo")

    bitacora = admin_service.bitacora(db)
    assert [r.nota for r in bitacora] == ["segundo", "primero"]


def test_el_detalle_del_negocio_trae_su_historial(db, admin, otro_usuario):
    admin_service.cambiar_suscripcion(db, admin, otro_usuario.id, sumar_dias(30), "pagó")

    negocio = admin_service.obtener_negocio(db, otro_usuario.id)
    assert len(negocio["historial"]) == 1
    assert negocio["historial"][0].nota == "pagó"


# --- Deshabilitar y permisos ---------------------------------------------

def test_deshabilitar_una_cuenta(db, admin, otro_usuario):
    admin_service.cambiar_activo(db, admin, otro_usuario.id, False, "uso indebido")

    db.refresh(otro_usuario)
    assert otro_usuario.activo is False


def test_no_puedes_deshabilitarte_a_ti_mismo(db, admin):
    with pytest.raises(ErrorNegocio):
        admin_service.cambiar_activo(db, admin, admin.id, False)


def test_un_admin_puede_marcar_a_su_socio(db, admin, otro_usuario):
    """Para no volver a entrar a Supabase después del primero."""
    admin_service.cambiar_admin(db, admin, otro_usuario.id, True, "socio")

    db.refresh(otro_usuario)
    assert otro_usuario.es_admin is True
    assert deps.exigir_admin(otro_usuario) is otro_usuario


def test_no_puedes_quitarte_a_ti_mismo_el_permiso(db, admin):
    """Si fueras el único administrador, el panel quedaría inaccesible para
    todos y habría que recuperarlo desde la base a mano."""
    with pytest.raises(ErrorNegocio) as exc:
        admin_service.cambiar_admin(db, admin, admin.id, False)
    assert "a ti mismo" in str(exc.value)


def test_a_otro_admin_si_se_le_puede_quitar(db, admin, otro_usuario):
    admin_service.cambiar_admin(db, admin, otro_usuario.id, True)
    admin_service.cambiar_admin(db, admin, otro_usuario.id, False, "ya no trabaja aquí")

    db.refresh(otro_usuario)
    assert otro_usuario.es_admin is False
