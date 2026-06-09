# perfil_html.py
"""Genera un reporte HTML exploratorio (ydata-profiling) de un cache parquet.

⚠️ Este script NO corre con el Python del proyecto (3.14): ydata-profiling
arrastra numba/llvmlite, que no tienen wheels para 3.14. Se ejecuta con el
entorno aparte `.venv-profiling` (Python 3.12), creado para esto:

    .venv-profiling\\Scripts\\python.exe perfil_html.py ruragro_ventas

Lee data/cache/<nombre>.parquet y escribe data/perfil/<nombre>.html.
Sin argumento, perfila todos los caches disponibles.
"""
import sys
from pathlib import Path

import pandas as pd
from ydata_profiling import ProfileReport

RAIZ = Path(__file__).resolve().parent
CACHE = RAIZ / "data" / "cache"
SALIDA = RAIZ / "data" / "perfil"


def perfilar_html(nombre: str) -> Path:
    ruta = CACHE / f"{nombre}.parquet"
    if not ruta.exists():
        raise FileNotFoundError(f"No existe {ruta}")
    df = pd.read_parquet(ruta)
    SALIDA.mkdir(parents=True, exist_ok=True)
    destino = SALIDA / f"{nombre}.html"
    # minimal=True desactiva correlaciones/interacciones pesadas → rápido en datasets grandes.
    rep = ProfileReport(df, title=f"Perfil exploratorio — {nombre}", minimal=True)
    rep.to_file(destino)
    print(f"✅ {nombre}: {len(df):,} filas → {destino}")
    return destino


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1:
        nombres = sys.argv[1:]
    else:
        nombres = [p.stem for p in sorted(CACHE.glob("*.parquet"))]
    for n in nombres:
        perfilar_html(n)
