"""
Leer plata escrita como la escribe la gente.

Estas pruebas son las más importantes del importador. Si falla la lectura
de "1.500", una tienda entera queda con los precios divididos por mil y
NADIE se entera hasta que cuadran la caja.
"""

import pytest

from app.core.numeros import NumeroInvalido, a_entero, a_numero


# --- El caso que puede arruinar una tienda --------------------------------

@pytest.mark.parametrize("texto,esperado", [
    ("1.500", 1500),          # mil quinientos, NO uno con cinco
    ("12.000", 12000),
    ("1.500.000", 1500000),
    ("900", 900),
    ("1.200", 1200),
])
def test_el_punto_de_miles_colombiano(texto, esperado):
    assert a_numero(texto) == esperado


def test_el_error_que_costaria_una_tienda():
    """Documenta explícitamente lo que NO debe pasar.

    float("1.500") da 1.5. Si el importador hiciera eso, el arroz quedaría
    a un peso cincuenta.
    """
    assert float("1.500") == 1.5        # lo que hace Python
    assert a_numero("1.500") == 1500.0  # lo que hace falta aquí


# --- Las otras formas en que llega la plata -------------------------------

@pytest.mark.parametrize("texto,esperado", [
    ("$1.500", 1500),           # con símbolo de peso
    ("$ 1.500", 1500),
    ("1500", 1500),             # sin separadores
    ("1500,50", 1500.5),        # coma decimal
    ("1.500,50", 1500.5),       # miles y decimales juntos
    ("0", 0),
    ("1,5", 1.5),               # uno y medio
    ("1.5", 1.5),               # pocos decimales: decimal normal
    ("COP 3.000", 3000),
])
def test_formas_habituales(texto, esperado):
    assert a_numero(texto) == esperado


def test_el_espacio_duro_que_mete_excel():
    """Excel al formatear como moneda inserta \\xa0, no un espacio normal.
    Sin quitarlo, el número no se parsea y la fila se rechaza sin motivo
    aparente."""
    assert a_numero("1.500\xa0") == 1500
    assert a_numero("$\xa01.500") == 1500


def test_acepta_numeros_ya_convertidos():
    """Excel a veces entrega la celda como número, no como texto. Ahí no
    hay separadores que interpretar."""
    assert a_numero(1500) == 1500
    assert a_numero(1500.5) == 1500.5


def test_formato_ingles_pegado():
    """Alguien que armó la plantilla con Excel en inglés."""
    assert a_numero("1,500.50") == 1500.5


# --- Lo que se rechaza ---------------------------------------------------

@pytest.mark.parametrize("malo", ["", "   ", None, "abc", "mil quinientos", "1.2.3,4,5", True])
def test_rechaza_lo_que_no_es_numero(malo):
    with pytest.raises(NumeroInvalido):
        a_numero(malo)


def test_el_mensaje_nombra_el_campo():
    """Para que el reporte pueda decir 'fila 47, columna precio' en vez de
    un error genérico que obliga a revisar 300 filas a mano."""
    with pytest.raises(NumeroInvalido) as exc:
        a_numero("abc", campo="precio")
    assert "precio" in str(exc.value)


def test_rechaza_un_numero_absurdamente_grande():
    """Casi siempre es un cero de más o un separador mal puesto."""
    with pytest.raises(NumeroInvalido) as exc:
        a_numero("999999999999")
    assert "demasiado grande" in str(exc.value)


# --- Cantidades ----------------------------------------------------------

def test_las_cantidades_son_enteras():
    assert a_entero("12") == 12
    assert a_entero("1.200") == 1200
    assert a_entero(12.0) == 12


def test_una_cantidad_con_decimales_se_rechaza():
    """Redondear en silencio esconde un error de captura dentro del
    inventario, donde nadie lo va a encontrar."""
    with pytest.raises(NumeroInvalido) as exc:
        a_entero("12,5")
    assert "entero" in str(exc.value)
