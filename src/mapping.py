# src/mapping.py
"""
Mapeo de las columnas crudas del reporte DIAN (en español, con tildes)
a nombres canónicos en snake_case que usa el resto del pipeline.

El emparejamiento se hace sobre el nombre NORMALIZADO (sin tildes, en
minúsculas, espacios colapsados) para ser robusto a diferencias de
codificación entre archivos.
"""
import unicodedata


def normalizar(nombre: str) -> str:
    """Quita tildes, pasa a minúsculas y colapsa espacios."""
    s = str(nombre).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


# nombre normalizado  ->  nombre canónico
MAPA_COLUMNAS = {
    "tipo de documento": "tipo_documento",
    "cufe/cude":         "cufe",
    "folio":             "folio",
    "prefijo":           "prefijo",
    "fecha emision":     "fecha_emision",
    "fecha recepcion":   "fecha_recepcion",
    "nit emisor":        "nit_emisor",
    "nombre emisor":     "nombre_emisor",
    "nit receptor":      "nit_receptor",
    "nombre receptor":   "nombre_receptor",
    "iva":               "iva",
    "total":             "valor",        # base sobre la que trabaja el transformer
    "rete iva":          "rete_iva",
    "rete renta":        "rete_renta",
    "rete ica":          "rete_ica",
    "estado":            "estado",
    "grupo":             "grupo",
}

# Columnas que el origen ya trae calculadas MANUALMENTE.
# Se omiten a propósito: el pipeline las recalcula desde 'valor' e 'iva'.
COLUMNAS_OMITIR = {
    "valor ajustado",
    "iva ajustado",
    "valor bruto",
}

# Sin estas no se puede procesar; el loader aborta si falta alguna.
COLUMNAS_REQUERIDAS = ["tipo_documento", "nit_emisor", "nit_receptor", "valor", "iva"]
