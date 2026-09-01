"""
entrenamiento/entrenar.py — Entrenar el clasificador de intenciones.

QUÉ ES ESTO Y QUÉ NO ES

No entrena una IA como la de Groq. Entrena un clasificador de texto, que es
estadística de toda la vida: sin GPU, sin API, sin tokens. Corre en un
portátil en segundos y el modelo resultante pesa unos cientos de kilobytes.

El trabajo que hace es el más pequeño posible: leer "q se me akaban los
produktos" y decir `lista_de_compra`. Nada más. No escribe respuestas y no
sabe cuántos productos hay — eso lo sigue calculando el enrutador contra la
base de datos, que es lo que hace que el número no se pueda inventar.

POR QUÉ NO VA EN requirements.txt

scikit-learn arrastra numpy y scipy: más de cien megas que el servidor de
producción no necesita para nada, porque entrenar se hace aquí, a mano, cada
tanto. Lo que sube a producción es el archivo del modelo, no la librería que
lo fabricó.

    pip install -r entrenamiento/requirements.txt

CÓMO SE USA

    python entrenamiento/entrenar.py

Lee los ejemplos etiquetados de la base, entrena, e imprime qué tan bien
quedó. Con `--guardar` escribe el modelo en entrenamiento/modelo.joblib.

OJO: lee de la base a la que apunte tu .env. Si ese .env es el de
producción, estás leyendo datos reales — solo lectura, pero conviene
saberlo.

CUÁNTOS DATOS HACEN FALTA, DE VERDAD

Con once intenciones, la referencia honesta es:

    ~50 por intención   → empieza a ser mejor que adivinar
    ~200 por intención  → sirve para producción
    menos de 20         → los números que salgan no significan nada

O sea, entre mil y dos mil ejemplos etiquetados. Pero ejecútalo desde HOY,
con los siete que tengas: el objetivo no es que acierte, es que la tubería
exista y que veas moverse los números. Cuando lleguen los datos, esto ya
está escrito y solo se vuelve a correr.
"""

import argparse
import sys
from collections import Counter

# Cuántos ejemplos por intención hacen falta. Son las referencias honestas
# para un clasificador de texto con esta cantidad de clases:
#
#   ÚTIL   — empieza a ser mejor que adivinar y ya se puede medir
#   BUENO  — se puede poner en producción sin sustos
#
# Por debajo de ÚTIL los números que salgan no significan nada, y creerles
# es peor que no tenerlos.
UTIL = 50
BUENO = 200

# --- Los ejemplos ---------------------------------------------------------
#
# Salen de dos sitios y los dos valen lo mismo: una etiqueta puesta a mano
# en el panel. La diferencia es que las de `valoraciones` vienen de una queja
# de un tendero, así que suelen ser los casos difíciles.

CONSULTA_SQL = """
SELECT pregunta, intencion_correcta
  FROM consultas
 WHERE estado = 'etiquetada'
   AND intencion_correcta IS NOT NULL
UNION ALL
SELECT pregunta, intencion_correcta
  FROM valoraciones
 WHERE intencion_correcta IS NOT NULL
"""


def cargar_ejemplos() -> tuple[list[str], list[str]]:
    """Los ejemplos etiquetados, tal como están en la base."""
    sys.path.insert(0, ".")
    from sqlalchemy import text
    from app.database.session import SessionLocal

    with SessionLocal() as db:
        filas = db.execute(text(CONSULTA_SQL)).all()

    return [f[0] for f in filas], [f[1] for f in filas]


def _informe_de_avance(conteo: Counter) -> None:
    """Cuánto falta para poder entrenar, intención por intención.

    Existe para que este script sirva DESDE HOY. Sin esto solo daría un
    error hasta dentro de meses; con esto es un medidor que se puede correr
    cada semana para ver si el conjunto avanza y, sobre todo, si avanza
    parejo.

    Lo parejo importa tanto como el total: mil ejemplos de una intención y
    tres de otra no entrenan nada. La columna de lo que falta es la que dice
    a cuáles hay que apuntar.
    """
    sys.path.insert(0, ".")
    from app.services.consulta_service import ETIQUETAS_VALIDAS

    total = sum(conteo.values())
    print("=" * 52)
    print(f"AVANCE DEL CONJUNTO — {total} de ~{UTIL * len(ETIQUETAS_VALIDAS)} "
          f"para poder entrenar")
    print("=" * 52)
    print(f"  {'intención':<20}{'tiene':>7}{'faltan':>9}\n")

    for intencion in ETIQUETAS_VALIDAS:
        tiene = conteo.get(intencion, 0)
        faltan = max(0, UTIL - tiene)
        marca = "  ✓" if faltan == 0 else ""
        print(f"  {intencion:<20}{tiene:>7}{faltan:>9}{marca}")

    listas = sum(1 for i in ETIQUETAS_VALIDAS if conteo.get(i, 0) >= UTIL)
    print(f"\n  {listas} de {len(ETIQUETAS_VALIDAS)} intenciones llegan a "
          f"{UTIL} ejemplos.")
    print(f"  Para producción conviene {BUENO} de cada una.\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guardar", action="store_true",
                        help="Escribe el modelo en entrenamiento/modelo.joblib")
    parser.add_argument("--minimo", type=int, default=3,
                        help="Intenciones con menos ejemplos que esto se descartan")
    args = parser.parse_args()

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import classification_report, confusion_matrix
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import make_pipeline
    except ImportError:
        print("Falta scikit-learn:  pip install -r entrenamiento/requirements.txt")
        return 1

    textos, etiquetas = cargar_ejemplos()
    print(f"{len(textos)} ejemplos etiquetados en la base.\n")

    conteo = Counter(etiquetas)
    for intencion, cuantos in conteo.most_common():
        print(f"  {cuantos:>5}  {intencion}")
    print()

    _informe_de_avance(conteo)

    # Una intención con dos ejemplos no se puede ni partir en entrenamiento y
    # prueba. Se descarta con un aviso en vez de reventar: es normal al
    # principio, cuando todavía no hay de todo.
    pocas = [i for i, c in conteo.items() if c < args.minimo]
    if pocas:
        print(f"Se descartan por tener menos de {args.minimo} ejemplos: "
              f"{', '.join(sorted(pocas))}\n")
        pares = [(t, e) for t, e in zip(textos, etiquetas) if e not in pocas]
        textos, etiquetas = [p[0] for p in pares], [p[1] for p in pares]

    if len(set(etiquetas)) < 2:
        print("Todavía no se puede entrenar: hace falta más de una intención\n"
              "con ejemplos suficientes. Arriba está lo que falta.")
        return 1

    # La partición estratificada necesita al menos un ejemplo de cada
    # intención en el 20% de prueba. Con pocos datos eso no se cumple, y el
    # error de scikit-learn no explica nada.
    if len(textos) * 0.2 < len(set(etiquetas)):
        print(f"Todavía no se puede evaluar: con {len(textos)} ejemplos y "
              f"{len(set(etiquetas))} intenciones, el 20% apartado para la\n"
              f"prueba no alcanza para tener uno de cada una. Hacen falta al "
              f"menos {len(set(etiquetas)) * 5} ejemplos\nrepartidos entre "
              f"ellas.\n\nArriba está lo que falta.")
        return 1

    # --- Partir en entrenamiento y prueba --------------------------------
    #
    # LA PARTE QUE MÁS SE HACE MAL. El 20% que se aparta NO se toca durante
    # el entrenamiento: es la única forma de saber si el modelo aprendió o
    # se memorizó los ejemplos. Un modelo evaluado con los mismos datos con
    # los que se entrenó saca 99% y falla en cuanto sale a producción.
    #
    # `stratify` mantiene la proporción de cada intención en las dos partes.
    # Sin eso, con clases desbalanceadas, una intención rara podría quedar
    # entera en una de las dos.
    x_entrena, x_prueba, y_entrena, y_prueba = train_test_split(
        textos, etiquetas, test_size=0.2, random_state=42, stratify=etiquetas,
    )

    # --- El modelo -------------------------------------------------------
    #
    # TfidfVectorizer convierte texto en números contando qué trozos
    # aparecen. Va por CARACTERES (3 a 5 seguidos) y no por palabras, y esa
    # es la decisión importante de todo el archivo:
    #
    #   "acaban" y "akaban" no comparten NINGUNA palabra, pero comparten los
    #   trozos "aban", "caba"/"kaba", "an". Por palabras serían dos cosas sin
    #   relación; por caracteres, casi la misma.
    #
    # Un tendero escribiendo rápido produce exactamente esa clase de
    # variación, así que ir por caracteres no es un detalle: es lo que hace
    # que el modelo aguante a los usuarios reales.
    #
    # LogisticRegression es el clasificador más simple que existe y para
    # texto corto en un dominio estrecho es difícil de superar. Nada de
    # redes neuronales: con dos mil ejemplos, algo más grande solo se
    # memoriza los datos.
    modelo = make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1),
        LogisticRegression(max_iter=1000, class_weight="balanced"),
    )
    modelo.fit(x_entrena, y_entrena)

    # --- Qué tan bien quedó ----------------------------------------------
    #
    # El acierto global miente cuando las clases están desbalanceadas: con
    # el 80% de los ejemplos en una intención, decir siempre esa saca 80% y
    # no sirve para nada. Por eso se mira intención por intención.
    print("=" * 62)
    print("QUÉ TAN BIEN QUEDÓ, INTENCIÓN POR INTENCIÓN")
    print("=" * 62)
    print("  precision = de las que dijo que eran X, cuántas lo eran")
    print("  recall    = de las que eran X, cuántas encontró")
    print("  support   = cuántas había en la prueba\n")
    print(classification_report(y_prueba, modelo.predict(x_prueba), zero_division=0))

    etiquetas_orden = sorted(set(y_prueba))
    print("Con qué se confunde (filas = lo que era, columnas = lo que dijo):\n")
    ancho = max(len(e) for e in etiquetas_orden) + 2
    print(" " * ancho + "".join(f"{e[:6]:>8}" for e in etiquetas_orden))
    matriz = confusion_matrix(y_prueba, modelo.predict(x_prueba), labels=etiquetas_orden)
    for nombre, fila in zip(etiquetas_orden, matriz):
        print(f"{nombre:<{ancho}}" + "".join(f"{n:>8}" for n in fila))

    # --- El umbral, que es lo que lo vuelve seguro -----------------------
    #
    # El modelo NUNCA dice "no sé": siempre devuelve la etiqueta más probable,
    # aunque sea con un 20% de confianza. Servir eso sería justo el fallo que
    # el enrutador entero está diseñado para evitar: responder con seguridad
    # algo que no era.
    #
    # Por eso en producción se le pone un piso: por debajo de esa confianza,
    # se aparta y responde el modelo de lenguaje. Es la misma regla de
    # siempre — perder cuesta una llamada, acertar de más no tiene arreglo.
    #
    # Esta tabla dice qué piso conviene: cuánto se responde y con cuánto
    # acierto en cada uno.
    print("\n" + "=" * 62)
    print("DÓNDE PONER EL PISO DE CONFIANZA")
    print("=" * 62)
    print(" umbral   responde   acierta de lo que responde\n")

    probabilidades = modelo.predict_proba(x_prueba)
    predicciones = modelo.classes_[probabilidades.argmax(axis=1)]
    confianzas = probabilidades.max(axis=1)

    for umbral in (0.0, 0.5, 0.6, 0.7, 0.8, 0.9):
        pasan = [i for i, c in enumerate(confianzas) if c >= umbral]
        if not pasan:
            print(f"  {umbral:>5.0%}        0%          —")
            continue
        aciertos = sum(1 for i in pasan if predicciones[i] == y_prueba[i])
        print(f"  {umbral:>5.0%}   {len(pasan)/len(y_prueba):>8.0%}   {aciertos/len(pasan):>15.0%}")

    print("\nBusca la fila donde acierta 95% o más. Ese es tu umbral: lo que\n"
          "no lo pase sigue yendo al modelo de lenguaje, como hoy.")

    if args.guardar:
        import joblib
        from pathlib import Path

        destino = Path(__file__).parent / "modelo.joblib"
        joblib.dump(modelo, destino)
        print(f"\nGuardado en {destino} ({destino.stat().st_size // 1024} KB)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
