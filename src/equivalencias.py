# src/equivalencias.py
"""
Equivalencias de NIT: unir un mismo tercero que llega escrito con dos NITs
distintos (normalmente el dígito de verificación pegado al final sin guion,
p. ej. 9016550371 → 901655037) para que el informe NO lo parta en dos filas.

La tabla la decide el usuario en config/nits_equivalentes.yaml (NIT a corregir
→ NIT correcto, el canónico que pide la DIAN, sin dígito de verificación):

    ruragro_ventas:
      "9016550371": "901655037"   # ECOGLOBAL ELIM SAS
      "183998122":  "18399812"    # JOVANNY RUBIANO LOPEZ
    default:                       # (opcional) aplica a todas las empresas
      "22222222": "222222222222"  # CONSUMIDOR FINAL

El pipeline une SOLO lo que esté en ese archivo (nunca a ciegas). La primera
vez, si no hay sección para la empresa, se prellena automáticamente con los
pares detectados con el mismo nombre (mismo_nombre=SI) para que el usuario los
revise; en las corridas siguientes la sección existente se respeta tal cual.
"""
import yaml
from pathlib import Path

RUTA_CONFIG = "config/nits_equivalentes.yaml"


def cargar_equivalencias(carpeta: str | None = None, ruta: str = RUTA_CONFIG) -> dict:
    """
    Devuelve el mapeo {nit_a_corregir: nit_correcto} para una empresa,
    combinando la sección 'default' con la específica de su `carpeta`.
    Claves/valores siempre como texto. Si no hay archivo, devuelve {}.
    """
    p = Path(ruta)
    if not p.exists():
        return {}

    with open(p, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    base = cfg.get("default") if isinstance(cfg.get("default"), dict) else {}
    propia = cfg.get(carpeta) if carpeta and isinstance(cfg.get(carpeta), dict) else {}

    mapa = {}
    for origen in (base, propia):
        for malo, bueno in origen.items():
            mapa[str(malo).strip()] = str(bueno).strip()
    return mapa


def aplicar_equivalencias(df, mapping: dict):
    """
    Reemplaza los NITs 'malos' por el canónico en nit_emisor y nit_receptor,
    para que el groupby posterior consolide el tercero en una sola fila.
    No toca los nombres (el informe ya elige el más frecuente por NIT).
    Devuelve (df, n_filas_corregidas).
    """
    if not mapping:
        return df, 0

    df = df.copy()
    cambiadas = 0
    for col in ("nit_emisor", "nit_receptor"):
        if col in df.columns:
            mask = df[col].isin(mapping)
            cambiadas += int(mask.sum())
            df[col] = df[col].where(~mask, df[col].map(mapping)).astype(df[col].dtype)
    if cambiadas:
        print(f"  🔗 Equivalencias de NIT aplicadas: {cambiadas:,} filas reasignadas "
              f"({len(mapping):,} NIT unificados)")
    return df, cambiadas


def asegurar_plantilla(carpeta: str, pares_si, ruta: str = RUTA_CONFIG) -> bool:
    """
    Si NO existe una sección para `carpeta` en el YAML, la añade prellenada con
    los pares de NIT detectados con el mismo nombre (para revisión). Si la
    sección ya existe, no toca nada (se respeta lo curado por el usuario).
    `pares_si` = lista de dicts con nit_largo, nit_corto y nombre_corto.
    Devuelve True si escribió la plantilla.
    """
    p = Path(ruta)
    cfg = {}
    if p.exists():
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    if carpeta in cfg or not pares_si:
        return False

    # Se escribe a mano (no yaml.dump) para conservar el comentario con el
    # nombre del tercero, que es lo que hace revisable el archivo.
    lineas = []
    if not p.exists():
        lineas.append(
            "# NIT a corregir -> NIT correcto (canónico, sin dígito de verificación).\n"
            "# Revisa cada par: borra los que no apliquen y agrega a mano los typos\n"
            "# que el detector no encuentra (p. ej. un dígito cambiado en el medio).\n"
        )
    lineas.append(f"\n{carpeta}:")
    for par in pares_si:
        nombre = str(par.get("nombre_corto", "")).strip()
        lineas.append(f'  "{par["nit_largo"]}": "{par["nit_corto"]}"   # {nombre}')

    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
    print(f"  📝 Plantilla de equivalencias creada para '{carpeta}' "
          f"({len(pares_si):,} pares) → {ruta}. Revísala y vuelve a correr el pipeline.")
    return True
