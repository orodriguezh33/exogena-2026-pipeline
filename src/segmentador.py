# src/segmentador.py
import re

import pandas as pd

from src.mapping import normalizar
from src.tipos import filtrar_por_tipos


def _nombre_representativo(s: pd.Series) -> str:
    """Nombre más frecuente del tercero (un mismo NIT puede traer variantes)."""
    m = s.dropna()
    if m.empty:
        return ""
    modo = m.mode()
    return str(modo.iloc[0]) if not modo.empty else str(m.iloc[0])


def reporte_cufes_repetidos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Lista los documentos cuyo CUFE/CUDE aparece más de una vez. El CUFE es
    único e irrepetible por documento, así que un CUFE repetido indica una
    fila cargada dos veces (doble conteo). Ordena por CUFE para revisarlos
    juntos. No los quita de los informes; solo los reporta.
    """
    if "cufe" not in df.columns:
        return pd.DataFrame()

    cufe = df["cufe"].astype("string").str.strip()
    con_cufe = df[cufe.notna() & (cufe != "")]
    dup = con_cufe[con_cufe.duplicated(subset="cufe", keep=False)].copy()

    if dup.empty:
        print("  ✅ Sin CUFE repetidos")
        return dup

    dup.insert(0, "veces", dup.groupby("cufe")["cufe"].transform("size"))
    cols = ["veces", "cufe", "tipo_documento", "folio", "fecha_emision",
            "nit_emisor", "nombre_emisor", "nit_receptor", "nombre_receptor",
            "valor", "iva", "archivo_origen"]
    dup = dup[[c for c in cols if c in dup.columns]].sort_values(
        ["cufe", "archivo_origen"], ignore_index=True
    )

    n_cufes = dup["cufe"].nunique()
    extra = len(dup) - n_cufes
    print(f"  🔁 CUFE repetidos: {n_cufes:,} CUFE en {len(dup):,} filas "
          f"({extra:,} filas de más por duplicado)")
    return dup


def reporte_emisor_igual_receptor(df: pd.DataFrame) -> pd.DataFrame:
    """
    Lista los documentos donde emisor == receptor (mismo NIT en ambos lados),
    CON sus valores. Pueden ser legítimos (p. ej. una estación que tanquea su
    propio vehículo) o un NIT mal digitado; por eso solo se REPORTAN para
    revisión y su valor SIEMPRE se mantiene en los totales.
    """
    mismo = df["nit_emisor"].notna() & (df["nit_emisor"] == df["nit_receptor"])
    registros = df[mismo].copy()
    if len(registros):
        print(f"  🪞 Emisor == receptor: {len(registros):,} registros "
              f"(se reportan; su valor se mantiene en los totales)")
    return registros


def _nombre_base(nombre: str) -> str:
    """Nombre normalizado a solo alfanuméricos en minúsculas (para comparar)."""
    return re.sub(r"[^a-z0-9]", "", normalizar(nombre))


def _mismo_tercero(a: str, b: str) -> bool:
    """¿Dos nombres parecen el mismo tercero? (uno contenido en el otro)."""
    na, nb = _nombre_base(a), _nombre_base(b)
    if len(na) < 4 or len(nb) < 4:
        return na == nb
    return na in nb or nb in na


def reporte_nits_sospechosos(informes: dict) -> pd.DataFrame:
    """
    Detecta NITs que probablemente sean el MISMO tercero escrito de dos
    formas: típicamente el dígito de verificación pegado al final sin guion
    (p. ej. 901655037 vs 9016550371). El groupby los cuenta como terceros
    distintos, así que el total del tercero queda partido en dos filas.

    NO modifica los totales: solo lista los pares (NIT corto vs NIT corto+1
    dígito) presentes en el MISMO informe, con sus nombres y valores, y marca
    'mismo_nombre' para distinguir un DV pegado real de una coincidencia
    casual (NIT distinto que por azar es otro NIT + un dígito). Revisar y
    corregir en el origen; nunca fusionar a ciegas.

    `informes` = {nombre_informe: (df_agrupado, col_nit, col_nombre)}.
    """
    filas = []
    for nombre_inf, (inf, col_nit, col_nombre) in informes.items():
        if inf.empty:
            continue
        nits = set(inf[col_nit].dropna().astype(str))
        # nombre y métricas por NIT para anexar a cada lado del par
        idx = inf.dropna(subset=[col_nit]).set_index(inf[col_nit].dropna().astype(str))
        for largo in nits:
            corto = largo[:-1]
            if len(largo) > 1 and largo[-1].isdigit() and corto in nits:
                rc, rl = idx.loc[corto], idx.loc[largo]
                filas.append({
                    "informe":        nombre_inf,
                    "nit_corto":      corto,
                    "nit_largo":      largo,
                    "nombre_corto":   rc[col_nombre],
                    "nombre_largo":   rl[col_nombre],
                    "mismo_nombre":   "SI" if _mismo_tercero(rc[col_nombre], rl[col_nombre]) else "NO",
                    "valor_corto":    rc["valor_bruto"],
                    "valor_largo":    rl["valor_bruto"],
                    "docs_corto":     int(rc["num_documentos"]),
                    "docs_largo":     int(rl["num_documentos"]),
                })

    if not filas:
        print("  ✅ Sin NITs sospechosos (mismo tercero con DV pegado)")
        return pd.DataFrame()

    rep = pd.DataFrame(filas).sort_values(
        ["mismo_nombre", "informe", "nit_corto"],
        ascending=[False, True, True], ignore_index=True,
    )
    probables = (rep["mismo_nombre"] == "SI").sum()
    print(f"  🪪 NITs sospechosos (posible DV pegado): {len(rep):,} pares "
          f"({probables:,} con el mismo nombre → probable mismo tercero; "
          f"revisar, no fusionar a ciegas)")
    return rep


def extraer_ventas(df: pd.DataFrame, nit_empresa: str, tipos: list[str]) -> pd.DataFrame:
    """Ventas = la empresa ES el emisor, solo los tipos de documento elegidos."""
    ventas = df[df["nit_emisor"] == nit_empresa]
    ventas = filtrar_por_tipos(ventas, tipos)
    print(f"  💰 Ventas (emisor = empresa, tipos elegidos): {len(ventas):,} registros")
    return ventas


def extraer_compras(df: pd.DataFrame, nit_empresa: str, tipos: list[str]) -> pd.DataFrame:
    """Compras = el emisor es un TERCERO (no la empresa), solo tipos elegidos."""
    compras = df[df["nit_emisor"] != nit_empresa]
    compras = filtrar_por_tipos(compras, tipos)
    print(f"  🛒 Compras (emisor ≠ empresa, tipos elegidos): {len(compras):,} registros")
    return compras


def extraer_soporte(df: pd.DataFrame, nit_empresa: str, tipos: list[str]) -> pd.DataFrame:
    """
    Documento soporte = la empresa ES el emisor (igual que ventas), pero
    seleccionando solo los tipos de documento soporte con no obligados.
    """
    soporte = df[df["nit_emisor"] == nit_empresa]
    soporte = filtrar_por_tipos(soporte, tipos)
    print(f"  📑 Documento soporte (emisor = empresa, tipos elegidos): {len(soporte):,} registros")
    return soporte


def _ultimo_cufe_por_nit(df: pd.DataFrame, col_nit: str) -> pd.Series:
    """CUFE de la factura más reciente (por fecha de emisión) de cada tercero."""
    d = df.copy()
    d["_f"] = pd.to_datetime(d["fecha_emision"], dayfirst=True, errors="coerce")
    return (
        d.sort_values("_f", kind="stable", na_position="first")
         .groupby(col_nit, dropna=False)["cufe"]
         .last()
         .rename("ultimo_cufe")
    )


def _agrupar(
    df: pd.DataFrame,
    col_nit: str,
    col_nombre: str,
    con_ultimo_cufe: bool = False,
) -> pd.DataFrame:
    """Suma valor_bruto e iva_ajustado por tercero (NIT)."""
    informe = (
        df.groupby(col_nit, dropna=False)
          .agg(
              nombre=(col_nombre, _nombre_representativo),
              valor_bruto=("valor_bruto", "sum"),
              iva_ajustado=("iva_ajustado", "sum"),
              num_documentos=("tipo_documento", "count"),
          )
          .reset_index()
          .rename(columns={"nombre": col_nombre})
          .sort_values("valor_bruto", ascending=False, ignore_index=True)
    )
    if con_ultimo_cufe and {"cufe", "fecha_emision"} <= set(df.columns):
        ultimo = _ultimo_cufe_por_nit(df, col_nit)
        informe = informe.merge(ultimo, left_on=col_nit, right_index=True, how="left")
    return informe


def informe_ventas(ventas: pd.DataFrame) -> pd.DataFrame:
    """Ventas agrupadas por NIT receptor (a quién se le vendió)."""
    inf = _agrupar(ventas, "nit_receptor", "nombre_receptor")
    print(f"  📊 Informe ventas: {len(inf):,} receptores")
    return inf


def informe_compras(compras: pd.DataFrame) -> pd.DataFrame:
    """Compras agrupadas por NIT emisor tercero (a quién se le compró).

    Incluye 'ultimo_cufe' (factura más reciente de cada emisor) para buscarla
    en el portal DIAN.
    """
    inf = _agrupar(compras, "nit_emisor", "nombre_emisor", con_ultimo_cufe=True)
    print(f"  📊 Informe compras: {len(inf):,} emisores")
    return inf


def informe_soporte(soporte: pd.DataFrame) -> pd.DataFrame:
    """Documento soporte agrupado por NIT receptor (el no obligado)."""
    inf = _agrupar(soporte, "nit_receptor", "nombre_receptor")
    print(f"  📊 Informe documento soporte: {len(inf):,} no obligados")
    return inf


def resumen_totales(
    ventas: pd.DataFrame,
    compras: pd.DataFrame,
    soporte: pd.DataFrame,
) -> pd.DataFrame:
    """
    Una fila por informe (ventas/compras/soporte) con nº de documentos,
    terceros distintos y las sumas de valor_ajustado, iva_ajustado y
    valor_bruto. En consola, además, se desglosa cada informe por tipo de
    documento para ver qué tipos elegidos suman hasta el TOTAL; la columna
    'tipos_incluidos' guarda esa lista en el CSV.
    """
    filas = []
    print("\n  📋 RESUMEN DE TOTALES (informes filtrados según tipos_documento.yaml)")
    for nombre, df, col_tercero in (
        ("ventas",  ventas,  "nit_receptor"),
        ("compras", compras, "nit_emisor"),
        ("soporte", soporte, "nit_receptor"),
    ):
        tipos = sorted(df["tipo_documento"].dropna().unique().tolist())
        filas.append({
            "informe":         nombre,
            "tipos_incluidos": " + ".join(tipos),
            "documentos":      len(df),
            "terceros":        int(df[col_tercero].nunique()),
            "valor_ajustado":  float(df["valor_ajustado"].sum()),
            "iva_ajustado":    float(df["iva_ajustado"].sum()),
            "valor_bruto":     float(df["valor_bruto"].sum()),
        })

        print(f"\n  {nombre.upper()}  (tipos elegidos en tipos_documento.yaml)")
        print(f"    {'tipo':<34}{'docs':>9}{'terceros':>10}{'valor_bruto':>20}{'iva_ajustado':>18}")
        print(f"    {'─'*33:<34}{'─'*8:>9}{'─'*9:>10}{'─'*19:>20}{'─'*17:>18}")
        if df.empty:
            print(f"    {'(sin registros)':<34}")
        else:
            g = (
                df.groupby("tipo_documento")
                  .agg(
                      documentos=("valor_bruto", "size"),
                      terceros=(col_tercero, "nunique"),
                      valor_bruto=("valor_bruto", "sum"),
                      iva_ajustado=("iva_ajustado", "sum"),
                  )
                  .reset_index()
                  .sort_values("valor_bruto", ascending=False, ignore_index=True)
            )
            for t in g.itertuples(index=False):
                print(f"    {str(t.tipo_documento)[:33]:<34}{t.documentos:>9,}{t.terceros:>10,}"
                      f"{t.valor_bruto:>20,.2f}{t.iva_ajustado:>18,.2f}")
        print(f"    {'— TOTAL —':<34}{len(df):>9,}{int(df[col_tercero].nunique()):>10,}"
              f"{float(df['valor_bruto'].sum()):>20,.2f}{float(df['iva_ajustado'].sum()):>18,.2f}")

    resumen = pd.DataFrame(filas)
    return resumen


def validacion_por_tipo(df: pd.DataFrame, nit_empresa: str) -> pd.DataFrame:
    """
    Validación: para CADA tipo de documento (sin filtrar por selección),
    cuántos terceros distintos hay y el total, separado por lado
    (ventas = emisor es la empresa, compras = emisor es un tercero).
    Incluye los tipos que suman $0 (p. ej. Application response), para
    poder contar el total real de terceros y decidir qué incluir.
    """
    lados = [
        ("ventas",  df[df["nit_emisor"] == nit_empresa], "nit_receptor"),
        ("compras", df[df["nit_emisor"] != nit_empresa], "nit_emisor"),
    ]

    partes = []
    print("\n  🔎 VALIDACIÓN POR TIPO DE DOCUMENTO (todos los tipos, SIN filtrar por tipos_documento.yaml)")
    print("     (solo separa por quién emitió el documento, no distingue compras/ventas/soporte)")
    for nombre, d, col in lados:
        g = (
            d.groupby("tipo_documento")
             .agg(
                 documentos=("valor_bruto", "size"),
                 terceros=(col, "nunique"),
                 valor_bruto=("valor_bruto", "sum"),
                 iva_ajustado=("iva_ajustado", "sum"),
             )
             .reset_index()
             .sort_values("documentos", ascending=False, ignore_index=True)
        )
        g.insert(0, "lado", nombre)

        total = pd.DataFrame([{
            "lado": nombre, "tipo_documento": "— TOTAL (terceros únicos) —",
            "documentos": len(d), "terceros": d[col].nunique(),
            "valor_bruto": d["valor_bruto"].sum(), "iva_ajustado": d["iva_ajustado"].sum(),
        }])
        partes.append(pd.concat([g, total], ignore_index=True))

        encabezado = ("DOCUMENTOS EMITIDOS POR LA EMPRESA (emisor = empresa)"
                      if nombre == "ventas"
                      else "DOCUMENTOS EMITIDOS POR TERCEROS (emisor ≠ empresa)")
        print(f"\n  {encabezado}")
        print(f"    {'tipo':<34}{'docs':>9}{'terceros':>10}{'valor_bruto':>20}")
        print(f"    {'─'*33:<34}{'─'*8:>9}{'─'*9:>10}{'─'*19:>20}")
        for r in g.itertuples(index=False):
            print(f"    {str(r.tipo_documento)[:33]:<34}{r.documentos:>9,}{r.terceros:>10,}{r.valor_bruto:>20,.2f}")
        print(f"    {'— TOTAL (terceros únicos) —':<34}{len(d):>9,}{d[col].nunique():>10,}{d['valor_bruto'].sum():>20,.2f}")

    return pd.concat(partes, ignore_index=True)


def subtotales_por_archivo(
    ventas: pd.DataFrame,
    compras: pd.DataFrame,
    soporte: pd.DataFrame,
) -> pd.DataFrame:
    """
    Subtotales de cada informe desglosados por archivo de origen
    (cuatrimestre) y por tipo de documento, con las mismas columnas que
    un pivote de verificación (Total, IVA, Valor/Iva Ajustado, Valor Bruto).
    """
    partes = []
    for nombre, d in (("ventas", ventas), ("compras", compras), ("soporte", soporte)):
        if d.empty:
            continue
        g = (
            d.groupby(["archivo_origen", "tipo_documento"])
             .agg(
                 documentos=("valor_bruto", "size"),
                 valor=("valor", "sum"),
                 iva=("iva", "sum"),
                 valor_ajustado=("valor_ajustado", "sum"),
                 iva_ajustado=("iva_ajustado", "sum"),
                 valor_bruto=("valor_bruto", "sum"),
             )
             .reset_index()
        )
        g.insert(1, "informe", nombre)
        partes.append(g)

    tabla = (
        pd.concat(partes, ignore_index=True)
          .sort_values(["archivo_origen", "informe", "tipo_documento"], ignore_index=True)
    )

    print("\n  📑 SUBTOTALES POR ARCHIVO Y TIPO DE DOCUMENTO")
    for (archivo, informe), bloque in tabla.groupby(["archivo_origen", "informe"], sort=False):
        print(f"\n  📄 {archivo}  →  {informe}")
        for r in bloque.itertuples(index=False):
            print(f"       {str(r.tipo_documento)[:32]:<33}{r.documentos:>8,} docs   "
                  f"bruto={r.valor_bruto:>20,.2f}   iva_aj={r.iva_ajustado:>15,.2f}")
        print(f"       {'└ SUBTOTAL':<33}{bloque.documentos.sum():>8,} docs   "
              f"bruto={bloque.valor_bruto.sum():>20,.2f}   iva_aj={bloque.iva_ajustado.sum():>15,.2f}")
    return tabla
