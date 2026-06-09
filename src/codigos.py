# src/codigos.py
"""
Asigna códigos DIAN de país / departamento / municipio a partir de los nombres
(que vienen del PDF, muy inconsistentes en mayúsculas, tildes y puntuación).

Fuente: data/codigos.csv — tres listas apiladas:
  - Departamentos: Nombre Departamentos, Codigo Departamentos
  - Municipios:    Codigo dep-mun (depto+municipio), Nombre Municipios, Codigo Municipios
  - Países:        Nombre Paises, Codigo Paises

Filosofía: normalizar fuerte y **reportar lo que no haga match** (nunca dejar
un código incorrecto en silencio). El municipio se busca DENTRO de su
departamento (hay nombres repetidos entre departamentos).
"""
import re

import pandas as pd

from src.mapping import normalizar

RUTA_CODIGOS = "data/codigos.csv"

# Variantes cortas de departamento que no aparecen literales en codigos.csv.
ALIAS_DEPTO = {
    "valle": "valle del cauca",
}


def _norm(s: str) -> str:
    """Normaliza para emparejar: sin tildes/mayúsculas, sin puntuación, 1 espacio."""
    s = normalizar(s)                 # quita tildes, minúsculas, colapsa espacios
    s = re.sub(r"[.,\-]", " ", s)     # puntos, comas, guiones → espacio
    return re.sub(r"\s+", " ", s).strip()


def _es_bogota(s: str) -> bool:
    """True para cualquier variante de Bogotá (incluye el mojibake 'Bogot�')."""
    return _norm(s).startswith("bogot")


def cargar_tablas(ruta: str = RUTA_CODIGOS) -> tuple[dict, dict, dict]:
    df = pd.read_csv(ruta, dtype=str, encoding="utf-8-sig").fillna("")
    deptos, paises, munis = {}, {}, {}
    for _, r in df.iterrows():
        nd = str(r["Nombre Departamentos"]).strip()
        if nd:
            deptos[_norm(nd)] = str(r["Codigo Departamentos"]).strip()
        npa = str(r["Nombre Paises"]).strip()
        if npa:
            paises[_norm(npa)] = str(r["Codigo Paises"]).strip()
        dm = str(r["Codigo dep-mun"]).strip()
        nm = str(r["Nombre Municipios"]).strip()
        if dm and nm:
            munis[(dm[:2], _norm(nm))] = (str(r["Codigo Municipios"]).strip(), dm)
    return deptos, paises, munis


def agregar_codigos(
    df: pd.DataFrame,
    ruta: str = RUTA_CODIGOS,
    col_pais: str = "pais",
    col_depto: str = "departamento",
    col_muni: str = "municipio",
) -> tuple[pd.DataFrame, dict]:
    """
    Agrega columnas codigo_pais, codigo_departamento, codigo_municipio y
    codigo_dep_mun. Devuelve (df_con_codigos, reporte_de_no_encontrados).
    """
    deptos, paises, munis = cargar_tablas(ruta)
    df = df.copy()

    cod_pais, cod_dep, cod_mun, cod_depmun = [], [], [], []
    sin_pais, sin_dep, sin_mun = set(), set(), set()

    for r in df.itertuples(index=False):
        d = {c: getattr(r, c, "") for c in (col_pais, col_depto, col_muni)}
        pais  = str(d[col_pais] or "")
        depto = str(d[col_depto] or "")
        muni  = str(d[col_muni] or "")

        # País
        cp = paises.get(_norm(pais), "")
        if pais.strip() and not cp:
            sin_pais.add(pais.strip())
        cod_pais.append(cp)

        # Departamento. Es Bogotá D.C. (11) si el depto es Bogotá, o si el
        # MUNICIPIO es Bogotá (p. ej. lo pusieron bajo "Cundinamarca").
        if _es_bogota(depto) or _es_bogota(muni):
            cd = "11"
        else:
            nd = _norm(depto)
            cd = deptos.get(nd, "") or deptos.get(ALIAS_DEPTO.get(nd, ""), "")
        if depto.strip() and not cd:
            sin_dep.add(depto.strip())
        cod_dep.append(cd)

        # Municipio: dentro del departamento. En Bogotá D.C. cualquier
        # localidad (Engativá, Fontibón, …) corresponde a 11001.
        cm, cdm = "", ""
        if cd == "11":
            cm, cdm = "001", "11001"
        elif cd and muni.strip():
            res = munis.get((cd, _norm(muni)))
            if res:
                cm, cdm = res
        if muni.strip() and not cm:
            sin_mun.add(f"{depto.strip()} | {muni.strip()}")
        cod_mun.append(cm)
        cod_depmun.append(cdm)

    df["codigo_pais"] = cod_pais
    df["codigo_departamento"] = cod_dep
    df["codigo_municipio"] = cod_mun
    df["codigo_dep_mun"] = cod_depmun

    reporte = {
        "pais":        sorted(sin_pais),
        "departamento": sorted(sin_dep),
        "municipio":   sorted(sin_mun),
    }
    return df, reporte
