# src/discovery.py
"""
Fase 1 — Discovery.

Inspecciona los .xlsm crudos de cada empresa y reporta, por archivo, qué
hoja contiene los datos y qué columnas trae (tipo y ejemplo). Sirve para
verificar que el mapeo de columnas (src/mapping.py) cubre lo que llega.

No es interactivo: la hoja de datos se detecta automáticamente.
"""
import pandas as pd
from pathlib import Path
from typing import Optional

from src.mapping import normalizar, MAPA_COLUMNAS, COLUMNAS_OMITIR


def _detectar_hoja_datos(archivo: Path) -> Optional[str]:
    requeridas = {"nit emisor", "total", "tipo de documento"}
    for hoja in pd.ExcelFile(archivo).sheet_names:
        norm = {normalizar(c) for c in pd.read_excel(archivo, sheet_name=hoja, nrows=0).columns}
        if requeridas <= norm:
            return hoja
    return None


def analizar_archivo(archivo: Path) -> dict:
    """Analiza un archivo y retorna su estructura de columnas."""
    hoja = _detectar_hoja_datos(archivo)
    if hoja is None:
        print(f"  ❌ {archivo.name}: no se encontró hoja de datos")
        return {}

    df = pd.read_excel(archivo, sheet_name=hoja, nrows=50)

    columnas = {}
    for col in df.columns:
        clave = normalizar(col)
        ejemplo = df[col].dropna()
        columnas[col] = {
            "normalizado": clave,
            "canonico":    MAPA_COLUMNAS.get(clave, "" if clave not in COLUMNAS_OMITIR else "(omitida)"),
            "tipo_dato":   str(df[col].dtype),
            "ejemplo":     str(ejemplo.iloc[0]) if not ejemplo.empty else "N/A",
        }

    return {"archivo": archivo.name, "hoja": hoja, "columnas": columnas}


def imprimir_reporte(nombre: str, reportes: list) -> None:
    print(f"\n{'─'*70}")
    print(f"  📊 REPORTE: {nombre}")
    print(f"{'─'*70}")

    if not reportes:
        print("  (sin archivos analizables)")
        return

    ref = reportes[0]
    print(f"  Hoja de datos detectada: {ref['hoja']}\n")
    print(f"  {'COLUMNA CRUDA':<28} {'→ CANÓNICO':<20} {'TIPO':<10} EJEMPLO")
    print(f"  {'─'*28} {'─'*20} {'─'*10} {'─'*20}")
    for col, info in ref["columnas"].items():
        canon = info["canonico"] or "⚠️ SIN MAPEAR"
        print(f"  {col[:28]:<28} {canon:<20} {info['tipo_dato']:<10} {info['ejemplo'][:25]}")

    # Consistencia de columnas entre archivos (periodos)
    sets = [set(r["columnas"].keys()) for r in reportes]
    comunes = set.intersection(*sets) if sets else set()
    todas = set().union(*sets) if sets else set()
    if todas - comunes:
        print(f"\n  ⚠️  Columnas que NO están en todos los archivos: {sorted(todas - comunes)}")
    else:
        print(f"\n  ✅ Columnas consistentes entre los {len(reportes)} archivos")


def correr_discovery(ruta_raw: str, empresas: list, anio: int) -> None:
    """Función principal del discovery."""
    print("\n🔍 FASE 1 — DISCOVERY DE COLUMNAS")
    print("=" * 70)

    for empresa in empresas:
        nombre  = empresa["nombre"]
        carpeta = empresa["carpeta"]
        ruta    = Path(ruta_raw) / carpeta

        if not ruta.exists():
            print(f"\n❌ Carpeta no encontrada: {ruta}")
            continue

        archivos = sorted(
            p for p in ruta.iterdir()
            if p.suffix.lower() in {".xlsm", ".xlsx"} and not p.name.startswith("~$")
        )
        reportes = [r for a in archivos if (r := analizar_archivo(a))]
        imprimir_reporte(nombre, reportes)

    print(f"\n{'='*70}")
    print("  Discovery completado.")
    print("  El mapeo de columnas vive en src/mapping.py (MAPA_COLUMNAS).")
    print("  Si aparece alguna columna 'SIN MAPEAR' que necesites, agrégala ahí.")
    print(f"{'='*70}\n")
