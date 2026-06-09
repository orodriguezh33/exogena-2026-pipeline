# tipos_runner.py
"""
Muestra qué tipos de documento hay en los datos de cada empresa,
separados por ventas y compras, marcando los que están seleccionados
en config/tipos_documento.yaml.

Úsalo para decidir qué tipos poner en ese YAML antes de correr el pipeline.

    uv run tipos_runner.py            # todas las empresas
    uv run tipos_runner.py ruragro    # solo una (carpeta, NIT o nombre)
"""
import sys
import argparse

from src.empresas import cargar_empresas, seleccionar_empresas
from src.loader   import cargar_periodos_empresa
from src.tipos    import cargar_seleccion, imprimir_tipos

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAW = "data/raw"


def main():
    parser = argparse.ArgumentParser(description="Lista los tipos de documento presentes en los datos.")
    parser.add_argument("empresa", nargs="?", default=None,
                        help="Solo una empresa (carpeta, NIT o nombre). Si se omite, todas.")
    args = parser.parse_args()

    empresas = seleccionar_empresas(cargar_empresas(), args.empresa)
    print("\n🔍 TIPOS DE DOCUMENTO EN LOS DATOS")
    print(f"  (✅ = seleccionado en config/tipos_documento.yaml para esa empresa)")

    for empresa in empresas:
        nit = str(empresa["nit"])
        print(f"\n{'='*55}")
        print(f"  🏢 {empresa['nombre']}  |  NIT: {nit}")
        print(f"{'='*55}")
        df = cargar_periodos_empresa(RAW, empresa["carpeta"])
        seleccion = cargar_seleccion(empresa["carpeta"])
        imprimir_tipos(df, nit, seleccion)


if __name__ == "__main__":
    main()
