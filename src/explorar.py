# src/explorar.py
"""Análisis exploratorio (EDA) del dataset usando solo pandas/numpy.

Pensado como alternativa a ydata-profiling / pandas-profiling, que hoy NO se
pueden instalar en Python 3.14 (arrastran numba/llvmlite, sin wheels para 3.14).
Este módulo no necesita dependencias extra: corre en el entorno actual.

Uso típico (en el notebook o en un script):

    from src.explorar import perfilar, cargar_cache
    df = cargar_cache("ruragro_ventas")     # lee data/cache/<nombre>.parquet
    perfilar(df)                             # imprime el perfil completo

`perfilar` solo imprime; `resumen_columnas(df)` devuelve un DataFrame con el
detalle por columna por si lo quieres exportar o seguir filtrando.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
CACHE = RAIZ / "data" / "cache"

# Columnas que tratamos como dinero (montos) si están presentes.
COLS_MONEDA = ("valor", "iva", "valor_ajustado", "iva_ajustado", "valor_bruto")
# Columnas de identificadores: no son números aunque parezcan (NIT, folio, CUFE).
COLS_ID = ("nit_emisor", "nit_receptor", "folio", "cufe", "cude", "prefijo")


def cargar_cache(nombre: str) -> pd.DataFrame:
    """Lee data/cache/<nombre>.parquet. Útil para explorar sin recorrer los .xlsm."""
    ruta = CACHE / f"{nombre}.parquet"
    if not ruta.exists():
        disponibles = ", ".join(p.stem for p in sorted(CACHE.glob("*.parquet")))
        raise FileNotFoundError(f"No existe {ruta}. Disponibles: {disponibles}")
    return pd.read_parquet(ruta)


def _fmt(n) -> str:
    """Formatea números grandes con separador de miles (estilo es-CO)."""
    try:
        if pd.isna(n):
            return "—"
    except (TypeError, ValueError):
        pass
    if isinstance(n, (int, np.integer)) or (isinstance(n, float) and float(n).is_integer()):
        return f"{int(n):,}".replace(",", ".")
    return f"{n:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def resumen_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por columna: tipo, nulos, % nulos, únicos y un par de ejemplos."""
    filas = []
    n = len(df)
    for c in df.columns:
        s = df[c]
        nulos = int(s.isna().sum())
        ejemplos = (
            s.dropna().astype(str).str.slice(0, 30).head(3).tolist()
        )
        filas.append({
            "columna": c,
            "tipo": str(s.dtype),
            "nulos": nulos,
            "%_nulos": round(100 * nulos / n, 1) if n else 0.0,
            "unicos": int(s.nunique(dropna=True)),
            "ejemplos": " | ".join(ejemplos),
        })
    return pd.DataFrame(filas)


def _seccion(titulo: str) -> None:
    print(f"\n{'─' * 70}\n  {titulo}\n{'─' * 70}")


def perfilar(df: pd.DataFrame, top: int = 10) -> None:
    """Imprime un perfil exploratorio completo del DataFrame.

    `top` = cuántos valores frecuentes mostrar por columna categórica.
    """
    _seccion("📦 RESUMEN GENERAL")
    n, m = df.shape
    mem = df.memory_usage(deep=True).sum() / 1024**2
    print(f"  Filas:     {_fmt(n)}")
    print(f"  Columnas:  {m}")
    print(f"  Memoria:   {mem:.1f} MB")
    dup = int(df.duplicated().sum())
    print(f"  Filas idénticas duplicadas: {_fmt(dup)}")

    _seccion("🧬 COLUMNAS (tipo · nulos · únicos · ejemplos)")
    with pd.option_context("display.max_colwidth", 35, "display.width", 200):
        print(resumen_columnas(df).to_string(index=False))

    # --- Fechas ---
    cols_fecha = [c for c in df.columns if "fecha" in c.lower()]
    if cols_fecha:
        _seccion("📅 FECHAS (rango y cobertura mensual)")
        for c in cols_fecha:
            f = pd.to_datetime(df[c], errors="coerce", dayfirst=True)
            val = f.notna().sum()
            if not val:
                print(f"  {c}: sin fechas válidas")
                continue
            print(f"  {c}: {f.min():%Y-%m-%d} → {f.max():%Y-%m-%d}  "
                  f"({_fmt(val)} válidas, {_fmt(df[c].isna().sum())} nulas)")
            por_mes = f.dt.to_period("M").value_counts().sort_index()
            for periodo, cnt in por_mes.items():
                barra = "█" * int(40 * cnt / por_mes.max())
                print(f"      {periodo}  {barra} {_fmt(cnt)}")

    # --- Montos ---
    cols_moneda = [c for c in COLS_MONEDA if c in df.columns]
    if cols_moneda:
        _seccion("💰 MONTOS (suma · promedio · mín · máx · negativos)")
        for c in cols_moneda:
            s = pd.to_numeric(df[c], errors="coerce")
            neg = int((s < 0).sum())
            cero = int((s == 0).sum())
            print(f"  {c}:")
            print(f"      suma={_fmt(s.sum())}  prom={_fmt(round(s.mean(), 2))}  "
                  f"mín={_fmt(s.min())}  máx={_fmt(s.max())}")
            print(f"      negativos={_fmt(neg)} (notas crédito)  ceros={_fmt(cero)}  "
                  f"nulos={_fmt(int(s.isna().sum()))}")

    # --- Categóricas / identificadores ---
    _seccion(f"🏷️  VALORES FRECUENTES (top {top})")
    cat = [c for c in df.columns
           if c not in cols_moneda and c not in cols_fecha
           and df[c].nunique(dropna=True) <= max(top * 5, 50) or c in (
               "tipo_documento", "estado", "grupo", "archivo_origen", "prefijo")]
    # Quitar duplicados conservando orden
    cat = list(dict.fromkeys(cat))
    for c in cat:
        vc = df[c].value_counts(dropna=False).head(top)
        if vc.empty:
            continue
        print(f"\n  {c}  ({_fmt(df[c].nunique(dropna=True))} valores únicos):")
        for val, cnt in vc.items():
            etiqueta = str(val)[:45]
            print(f"      {cnt:>10,}".replace(",", ".") + f"  {etiqueta}")

    # --- Chequeos propios del dominio exógena ---
    _seccion("🔎 CHEQUEOS DE DOMINIO (exógena)")
    if "cufe" in df.columns:
        reps = df["cufe"].value_counts()
        reps = reps[reps > 1]
        print(f"  CUFE repetidos: {_fmt(len(reps))} CUFE aparecen >1 vez "
              f"({_fmt(int(reps.sum() - len(reps)))} filas de más potenciales)")
    if {"nit_emisor", "nit_receptor"} <= set(df.columns):
        ig = int((df["nit_emisor"].astype(str) == df["nit_receptor"].astype(str)).sum())
        print(f"  emisor == receptor: {_fmt(ig)} filas (revisar, no se eliminan)")
    if "tipo_documento" in df.columns:
        nc = df["tipo_documento"].astype(str).str.normalize("NFKD") \
            .str.encode("ascii", "ignore").str.decode("ascii").str.lower()
        n_nc = int(nc.str.contains("nota de credito").sum())
        print(f"  Notas de crédito (por tipo_documento): {_fmt(n_nc)} filas")

    print(f"\n{'═' * 70}\n  ✅ Perfil terminado.\n{'═' * 70}")


if __name__ == "__main__":
    import sys
    nombre = sys.argv[1] if len(sys.argv) > 1 else "ruragro_ventas"
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Explorando cache: {nombre}")
    perfilar(cargar_cache(nombre))
