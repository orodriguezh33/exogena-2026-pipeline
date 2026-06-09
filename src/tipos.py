# src/tipos.py
"""
Descubrimiento y selección de tipos de documento.

- resumen_tipos / imprimir_tipos: muestran qué tipos hay en los datos,
  separados por el lado de ventas (la empresa emite) y de compras
  (emite un tercero).
- cargar_seleccion: lee config/tipos_documento.yaml.
- filtrar_por_tipos: deja solo los tipos elegidos (comparando sin tildes
  ni mayúsculas).
- verificar_seleccion: avisa de desajustes entre lo configurado y lo real.
"""
import yaml
import pandas as pd
from pathlib import Path

from src.mapping import normalizar

RUTA_CONFIG = "config/tipos_documento.yaml"

_DEFECTO = {
    "ventas":  ["Factura electrónica", "Nota de crédito electrónica"],
    "compras": ["Factura electrónica", "Nota de crédito electrónica"],
    "soporte": ["Documento soporte con no obligados"],
}

# Informes donde la empresa es el emisor (lado "ventas") vs. emisor tercero.
LADO_EMISOR_EMPRESA = ("ventas", "soporte")
LADO_EMISOR_TERCERO = ("compras",)


def _base_default(cfg: dict) -> dict:
    """Selección base: la clave 'default', o las listas en la raíz (formato plano)."""
    if isinstance(cfg.get("default"), dict):
        return cfg["default"]
    return {k: cfg[k] for k in _DEFECTO if k in cfg}


def cargar_seleccion(carpeta: str | None = None, ruta: str = RUTA_CONFIG) -> dict:
    """
    Devuelve los tipos seleccionados para una empresa (por su `carpeta`),
    combinando el 'default' con el override específico de esa empresa.
    Si no existe el archivo, usa el defecto interno.
    """
    p = Path(ruta)
    if not p.exists():
        print(f"  ⚠️  {ruta} no existe — uso selección por defecto "
              f"(factura electrónica + nota crédito)")
        return dict(_DEFECTO)

    with open(p, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    base = _base_default(cfg)
    override = cfg.get(carpeta) if carpeta else None
    if not isinstance(override, dict):
        override = {}

    # Por cada lado: empresa > default > defecto interno.
    return {
        clave: override.get(clave) or base.get(clave) or _DEFECTO[clave]
        for clave in _DEFECTO
    }


def resumen_tipos(df: pd.DataFrame, nit_empresa: str) -> tuple[pd.Series, pd.Series]:
    """Conteo de tipo_documento en el lado ventas y en el lado compras."""
    ventas  = df.loc[df["nit_emisor"] == nit_empresa, "tipo_documento"].value_counts()
    compras = df.loc[df["nit_emisor"] != nit_empresa, "tipo_documento"].value_counts()
    return ventas, compras


def imprimir_tipos(df: pd.DataFrame, nit_empresa: str, seleccion: dict | None = None) -> None:
    """Muestra los tipos disponibles y marca cuáles están seleccionados."""
    ventas, compras = resumen_tipos(df, nit_empresa)

    def _norm_set(lista):
        return {normalizar(t) for t in (lista or [])}

    sel_v = _norm_set(seleccion["ventas"])  if seleccion else set()
    sel_c = _norm_set(seleccion["compras"]) if seleccion else set()

    def _tabla(titulo, conteo, seleccionados):
        print(f"\n  📄 TIPOS DE DOCUMENTO — {titulo}")
        print(f"  {'usar':<6}{'tipo':<45}{'registros':>10}")
        print(f"  {'─'*4:<6}{'─'*43:<45}{'─'*9:>10}")
        for tipo, n in conteo.items():
            marca = "✅" if normalizar(tipo) in seleccionados else "  "
            print(f"  {marca:<6}{str(tipo)[:43]:<45}{n:>10,}")

    _tabla("VENTAS (la empresa emite)", ventas, sel_v)
    _tabla("COMPRAS (emite un tercero)", compras, sel_c)


def verificar_seleccion(df: pd.DataFrame, nit_empresa: str, seleccion: dict) -> None:
    """Avisa si se seleccionó un tipo inexistente o si hay tipos sin usar."""
    ventas, compras = resumen_tipos(df, nit_empresa)
    presentes_emisor_empresa = {normalizar(t) for t in ventas.index}
    presentes_emisor_tercero = {normalizar(t) for t in compras.index}

    for lado, presentes in (
        *[(l, presentes_emisor_empresa) for l in LADO_EMISOR_EMPRESA],
        *[(l, presentes_emisor_tercero) for l in LADO_EMISOR_TERCERO],
    ):
        elegidos = {normalizar(t) for t in seleccion.get(lado, [])}
        fantasma = elegidos - presentes
        if fantasma:
            print(f"  ⚠️  [{lado}] tipos configurados que NO aparecen en los datos: {sorted(fantasma)}")


def filtrar_por_tipos(df: pd.DataFrame, tipos: list[str]) -> pd.DataFrame:
    """Deja solo las filas cuyo tipo_documento está en la lista (sin tildes/case)."""
    permitidos = {normalizar(t) for t in tipos}
    mask = df["tipo_documento"].map(normalizar).isin(permitidos)
    return df[mask].copy()
