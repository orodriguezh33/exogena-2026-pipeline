# crear_db.py
"""
Consolida los parquet de cache de cada empresa en una sola base SQLite,
con UNA TABLA POR EMPRESA (nombre de tabla = carpeta).

    uv run crear_db.py                # todas las empresas → data/db/exogena.db
    uv run crear_db.py arias_correa   # solo una (carpeta, NIT o nombre)
    uv run crear_db.py --salida mi.db # ruta de la base distinta

Lee directo de data/cache/<carpeta>.parquet (instantáneo). Si falta el
cache de una empresa, corre antes:  uv run ingestar.py <empresa>

SQLite no necesita servidor ni dependencias extra (sqlite3 es stdlib).
Abre la base con DB Browser for SQLite, DBeaver, o desde Python/pandas.
"""
import sys
import sqlite3
import argparse
from pathlib import Path

import pandas as pd

from src.empresas import cargar_empresas, seleccionar_empresas

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE  = Path("data/cache")
SALIDA = "data/db/exogena.db"


def main():
    parser = argparse.ArgumentParser(description="Vuelca los parquet de cache a una base SQLite (una tabla por empresa).")
    parser.add_argument("empresa", nargs="?", default=None,
                        help="Solo una empresa (carpeta, NIT o nombre). Si se omite, todas.")
    parser.add_argument("--salida", default=SALIDA, help=f"Ruta de la base SQLite (def. {SALIDA}).")
    args = parser.parse_args()

    empresas = seleccionar_empresas(cargar_empresas(), args.empresa)
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n🗄️  Creando base SQLite → {salida}")
    con = sqlite3.connect(salida)
    try:
        for empresa in empresas:
            carpeta = empresa["carpeta"]
            parquet = CACHE / f"{carpeta}.parquet"
            if not parquet.exists():
                print(f"  ⏭️  {carpeta}: sin cache ({parquet}). Corre 'uv run ingestar.py {carpeta}'.")
                continue

            df = pd.read_parquet(parquet)
            df.to_sql(carpeta, con, if_exists="replace", index=False)
            print(f"  ✅ {carpeta:<18} {len(df):>8,} filas → tabla '{carpeta}'")
    finally:
        con.close()

    print(f"\n✨ Listo. {salida}")


if __name__ == "__main__":
    main()
