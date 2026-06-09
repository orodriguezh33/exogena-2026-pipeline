# ingestar.py
"""
FASE 0 — Ingesta: lee los Excel de cada empresa y construye el caché Parquet
en data/cache/<empresa>.parquet.

Leer los .xlsm es lo lento (varios minutos). Hazlo UNA vez al inicio; después
tipos_runner.py y pipeline.py leen del caché (segundos).

    uv run ingestar.py                 # todas las empresas del config
    uv run ingestar.py ruragro         # solo una (carpeta / NIT / nombre)
    uv run ingestar.py ruragro --refrescar   # re-lee los Excel aunque haya caché
"""
import sys
import argparse

from src.empresas import cargar_empresas, seleccionar_empresas
from src.loader import cargar_periodos_empresa

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAW = "data/raw"


def main():
    ap = argparse.ArgumentParser(description="Construye el caché Parquet leyendo los Excel.")
    ap.add_argument("empresa", nargs="?", default=None,
                    help="Solo una empresa (carpeta / NIT / nombre). Si se omite, todas.")
    ap.add_argument("--refrescar", action="store_true",
                    help="Re-lee los Excel aunque ya exista caché.")
    args = ap.parse_args()

    empresas = seleccionar_empresas(cargar_empresas(), args.empresa)

    print("\n📦 INGESTA → caché Parquet")
    for emp in empresas:
        print(f"\n{'='*55}\n  🏢 {emp['nombre']}  ({emp['carpeta']})\n{'='*55}")
        cargar_periodos_empresa(RAW, emp["carpeta"], usar_cache=not args.refrescar)

    print(f"\n{'='*55}")
    print("  ✅ Caché listo. tipos_runner y pipeline ya leen del caché (rápido).")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
