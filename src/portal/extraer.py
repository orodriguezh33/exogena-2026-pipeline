# src/portal/extraer.py
"""
Parsea los datos del tercero (emisor) de la 1ra página de una factura PDF.

Recorta la sección "Datos del Emisor … Datos del Adquiriente" y extrae los
campos por regex de alternancia de etiquetas. Adaptado de
busqueda_portal/extraer_emisores.py.
"""
from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

# Etiquetas tal como aparecen en el PDF DIAN, en el orden esperado.
CAMPOS = [
    "Razón Social",
    "Nombre Comercial",
    "Nit del Emisor",
    "Tipo de Contribuyente",
    "Régimen Fiscal",
    "Responsabilidad tributaria",
    "Actividad Económica",
    "País",
    "Departamento",
    "Municipio / Ciudad",
    "Dirección",
    "Teléfono / Móvil",
    "Correo",
]

_ALT = "|".join(re.escape(c) for c in CAMPOS)
_RE_CAMPO = re.compile(
    r"(?P<label>" + _ALT + r")\s*:\s*(?P<valor>.*?)"
    r"(?=\s*(?:" + _ALT + r")\s*:|$)",
    re.IGNORECASE | re.DOTALL,
)


def _texto_emisor(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    if not reader.pages:
        return ""
    texto = reader.pages[0].extract_text() or ""
    m = re.search(
        r"Datos del Emisor.*?(?=Datos del Adquiriente|Datos del Comprador)",
        texto, re.DOTALL | re.IGNORECASE,
    )
    return m.group(0) if m else texto


def _canon(label: str) -> str | None:
    for c in CAMPOS:
        if c.lower() == label.lower():
            return c
    return None


def extraer_datos_pdf(pdf_path: Path) -> dict:
    """Devuelve un dict con los campos de CAMPOS parseados del PDF."""
    texto = _texto_emisor(pdf_path)
    datos = {c: "" for c in CAMPOS}
    for m in _RE_CAMPO.finditer(texto):
        canon = _canon(m.group("label"))
        if not canon or datos[canon]:
            continue
        datos[canon] = re.sub(r"\s+", " ", m.group("valor")).strip()
    return datos
