# src/loader.py
import pandas as pd
from pathlib import Path

from src.mapping import (
    normalizar,
    MAPA_COLUMNAS,
    COLUMNAS_OMITIR,
    COLUMNAS_REQUERIDAS,
)

# NITs que el pipeline trata como texto (no como número).
_COLS_TEXTO = ["nit_emisor", "nit_receptor", "folio"]

# Columnas de fecha. Según el archivo, Excel las trae como fecha real
# (datetime) o como texto; al concatenar quedaría una columna 'object' con
# tipos mezclados que pyarrow no puede escribir a Parquet. Se normalizan a
# datetime64 para unificar el tipo (aguas abajo siempre se reinterpretan con
# pd.to_datetime dayfirst, así que esto es consistente).
_COLS_FECHA = ["fecha_emision", "fecha_recepcion"]


def _limpiar_codigo(serie: pd.Series) -> pd.Series:
    """
    Normaliza NITs/folios a texto limpio. Algunos archivos leen estas
    columnas como número (p. ej. por un NaN en la columna), dejando
    '900951054.0' en vez de '900951054'; aquí se quita ese sufijo decimal
    para que el mismo NIT siempre coincida entre archivos.
    """
    s = serie.astype("string").str.strip()
    s = s.str.replace(r"\.0+$", "", regex=True)
    return s


def _detectar_hoja_datos(archivo: Path) -> str:
    """
    Un .xlsm del reporte DIAN trae varias hojas (la de datos 'Rp_Doc_*',
    una 'DOCS' vacía, a veces resúmenes manuales). Detecta la hoja real
    leyendo solo los encabezados y buscando las columnas clave.
    """
    xl = pd.ExcelFile(archivo)
    requeridas = {"nit emisor", "total", "tipo de documento"}

    for hoja in xl.sheet_names:
        encabezados = pd.read_excel(archivo, sheet_name=hoja, nrows=0).columns
        norm = {normalizar(c) for c in encabezados}
        if requeridas <= norm:
            return hoja

    raise ValueError(
        f"No se encontró una hoja de datos válida en {archivo.name}. "
        f"Hojas disponibles: {xl.sheet_names}"
    )


def _cargar_archivo(archivo: Path) -> pd.DataFrame:
    """Lee un .xlsm, renombra columnas a canónicas y descarta las manuales."""
    hoja = _detectar_hoja_datos(archivo)
    df = pd.read_excel(archivo, sheet_name=hoja)

    # Renombrar a canónico; lo no mapeado y lo omitido se descarta.
    renombrar = {}
    for col in df.columns:
        clave = normalizar(col)
        if clave in COLUMNAS_OMITIR:
            continue
        if clave in MAPA_COLUMNAS:
            renombrar[col] = MAPA_COLUMNAS[clave]

    df = df[list(renombrar.keys())].rename(columns=renombrar)

    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        raise ValueError(
            f"{archivo.name} (hoja '{hoja}') no tiene las columnas "
            f"requeridas: {faltantes}"
        )

    for col in _COLS_TEXTO:
        if col in df.columns:
            df[col] = _limpiar_codigo(df[col])

    for col in _COLS_FECHA:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")

    df["archivo_origen"] = archivo.name
    print(f"  ✅ {archivo.name} [{hoja}]: {len(df):,} registros")
    return df


CACHE_DIR = "data/cache"


def cargar_periodos_empresa(
    ruta_raw: str,
    carpeta_empresa: str,
    usar_cache: bool = True,
) -> pd.DataFrame:
    """
    Carga TODOS los .xlsm/.xlsx de la carpeta de una empresa y los
    consolida en un único DataFrame con columnas canónicas.

    Leer Excel es lento; por eso el resultado se guarda en
    data/cache/<empresa>.parquet. Si la caché existe y es más nueva que
    todos los Excel de origen, se lee de ahí (milisegundos). La caché es
    independiente de config/tipos_documento.yaml (guarda los datos crudos
    mapeados), así que cambiar la selección de tipos NO requiere refrescarla;
    usa usar_cache=False solo si cambió el origen o la lógica de carga.
    """
    ruta = Path(ruta_raw) / carpeta_empresa
    if not ruta.exists():
        raise FileNotFoundError(f"Carpeta no encontrada: {ruta}")

    archivos = sorted(
        p for p in ruta.iterdir()
        if p.suffix.lower() in {".xlsm", ".xlsx"} and not p.name.startswith("~$")
    )
    if not archivos:
        raise FileNotFoundError(f"No se encontraron archivos Excel en: {ruta}")

    cache = Path(CACHE_DIR) / f"{carpeta_empresa}.parquet"
    if usar_cache and cache.exists():
        if cache.stat().st_mtime >= max(a.stat().st_mtime for a in archivos):
            df = pd.read_parquet(cache)
            print(f"  ⚡ Caché: {len(df):,} registros "
                  f"(data/cache/{carpeta_empresa}.parquet)")
            return df

    partes = [_cargar_archivo(a) for a in archivos]
    df = pd.concat(partes, ignore_index=True)
    print(f"  📊 Total consolidado: {len(df):,} registros")

    # Las columnas de texto (p. ej. nombre_receptor) pueden traer celdas
    # numéricas en unos archivos y texto en otros, quedando 'object' con
    # tipos mezclados que pyarrow no puede escribir. Se uniforman a string.
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype("string")

    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    print(f"  💾 Caché guardada → data/cache/{carpeta_empresa}.parquet")
    return df
