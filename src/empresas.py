# src/empresas.py
"""Carga y selección de empresas desde config/empresas.yaml."""
import sys
import yaml

RUTA_CONFIG = "config/empresas.yaml"


def cargar_empresas(ruta: str = RUTA_CONFIG) -> list[dict]:
    with open(ruta, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    return config.get("empresas", [])


def _coincide(empresa: dict, filtro: str) -> bool:
    f = filtro.strip().lower()
    carpeta = str(empresa.get("carpeta", "")).lower()
    nit     = str(empresa.get("nit", "")).lower()
    nombre  = str(empresa.get("nombre", "")).lower()
    # coincidencia exacta por carpeta/nit, o parcial por nombre
    return f in (carpeta, nit) or f in nombre


def seleccionar_empresas(empresas: list[dict], filtro: str | None) -> list[dict]:
    """
    Devuelve las empresas que coinciden con `filtro` (carpeta, NIT o parte
    del nombre). Sin filtro, devuelve todas. Aborta si el filtro no coincide.
    """
    if not filtro:
        return empresas

    seleccionadas = [e for e in empresas if _coincide(e, filtro)]
    if not seleccionadas:
        disponibles = ", ".join(e.get("carpeta", "?") for e in empresas)
        print(f"❌ Ninguna empresa coincide con '{filtro}'. Disponibles: {disponibles}")
        sys.exit(1)
    return seleccionadas
