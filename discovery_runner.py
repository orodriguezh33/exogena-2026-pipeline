# discovery_runner.py
#
#     uv run discovery_runner.py            # todas las empresas
#     uv run discovery_runner.py ruragro    # solo una (carpeta, NIT o nombre)
import sys
import argparse

from src.empresas  import cargar_empresas, seleccionar_empresas
from src.discovery import correr_discovery

# Evita que la consola de Windows (cp1252) aborte al imprimir emojis/tildes.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ANIO = 2025

parser = argparse.ArgumentParser(description="Inspecciona las columnas de los archivos crudos.")
parser.add_argument("empresa", nargs="?", default=None,
                    help="Solo una empresa (carpeta, NIT o nombre). Si se omite, todas.")
args = parser.parse_args()

empresas = seleccionar_empresas(cargar_empresas(), args.empresa)

correr_discovery(
    ruta_raw = "data/raw",
    empresas = empresas,
    anio     = ANIO,
)
