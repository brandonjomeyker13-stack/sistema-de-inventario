"""
Un nombre de negocio en blanco tumbaba el registro.

El fallo: el schema exigía `min_length=1`, y "   " tiene tres caracteres,
así que pasaba. Después el repositorio le hace .strip() antes de guardar y
llegaba VACÍO a la base, donde una restricción lo rechazaba. Resultado: un
error 500 al registrarse, por un campo que alguien rellenó con la barra
espaciadora.

En el login con Google era peor todavía: el servicio elige el nombre con
`nombre_negocio or datos.get("name")`, y una cadena de espacios es TRUTHY —
ganaba sobre el nombre real que manda Google y llegaba vacía igual.
"""

import pytest
from pydantic import ValidationError

from app.schemas.auth import GoogleLogin, UsuarioRegistro
from app.schemas.usuario import UsuarioActualizar


@pytest.mark.parametrize("blanco", ["   ", "\t", " \n ", "  \t  "])
def test_el_registro_rechaza_un_nombre_en_blanco(blanco):
    """422 explicando el campo, no un 500 del servidor."""
    with pytest.raises(ValidationError):
        UsuarioRegistro(email="a@b.com", password="clave12345", nombre_negocio=blanco)


def test_el_registro_colapsa_los_espacios_internos(nombre="Tienda   La   Esquina"):
    """Igual que en productos: "Tienda  La" con doble espacio se ve idéntico
    a "Tienda La" pero sería otro negocio."""
    u = UsuarioRegistro(email="a@b.com", password="clave12345", nombre_negocio=nombre)
    assert u.nombre_negocio == "Tienda La Esquina"


def test_editar_el_perfil_tambien_rechaza_el_blanco():
    with pytest.raises(ValidationError):
        UsuarioActualizar(nombre_negocio="   ")


@pytest.mark.parametrize("blanco", ["   ", "\t", ""])
def test_en_google_un_nombre_en_blanco_se_vuelve_None(blanco):
    """None y no "": el servicio elige con `nombre_negocio or ...`, y una
    cadena de espacios es truthy — ganaría sobre el nombre de Google."""
    g = GoogleLogin(id_token="x", nombre_negocio=blanco)
    assert g.nombre_negocio is None


def test_en_google_el_nombre_de_verdad_se_conserva():
    g = GoogleLogin(id_token="x", nombre_negocio="Papelería Sol")
    assert g.nombre_negocio == "Papelería Sol"


def test_asi_el_nombre_de_google_gana_cuando_el_campo_viene_vacio():
    """La consecuencia práctica del cambio anterior: con None, el `or` del
    servicio pasa al siguiente valor, que es el nombre de la cuenta de
    Google."""
    g = GoogleLogin(id_token="x", nombre_negocio="   ")
    elegido = g.nombre_negocio or "Nombre desde Google"
    assert elegido == "Nombre desde Google"
