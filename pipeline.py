# pipeline.py
import sys
import argparse
from pathlib import Path

from src.empresas    import cargar_empresas, seleccionar_empresas
from src.loader      import cargar_periodos_empresa
from src.transformer import aplicar_transformaciones
from src.tipos       import cargar_seleccion, imprimir_tipos, verificar_seleccion
from src.equivalencias import (
    cargar_equivalencias, aplicar_equivalencias, asegurar_plantilla,
)
from src.segmentador import (
    reporte_emisor_igual_receptor, reporte_cufes_repetidos, validacion_por_tipo,
    reporte_nits_sospechosos,
    extraer_ventas, extraer_compras, extraer_soporte,
    informe_ventas, informe_compras, informe_soporte,
    resumen_totales, subtotales_por_archivo,
)
from src.exportar import escribir_csv

# La consola de Windows (cp1252) no puede imprimir emojis/tildes y aborta;
# forzamos UTF-8 para que los mensajes no rompan la ejecución.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Configuración ──────────────────────────────────────
ANIO      = 2025
RAW       = "data/raw"
PROCESSED = "data/processed"
OUTPUT    = "data/output"
# ───────────────────────────────────────────────────────


def procesar_empresa(empresa: dict, usar_cache: bool = True) -> None:
    nombre  = empresa["nombre"]
    nit     = str(empresa["nit"])
    carpeta = empresa["carpeta"]

    print(f"\n{'='*55}")
    print(f"  🏢 {nombre}  |  NIT: {nit}")
    print(f"{'='*55}")

    # Selección de tipos de documento propia de esta empresa (o el default).
    seleccion = cargar_seleccion(carpeta)

    # ── 1. Cargar todos los periodos de esta empresa ──
    df_raw = cargar_periodos_empresa(RAW, carpeta, usar_cache=usar_cache)

    # Aviso temprano si el NIT está mal configurado (no aparece como emisor):
    # en ese caso ventas y soporte saldrían vacíos sin razón aparente.
    if (df_raw["nit_emisor"] == nit).sum() == 0:
        print(f"  ⚠️  ¡ATENCIÓN! El NIT '{nit}' no aparece como emisor en los datos. "
              f"Revisa el campo 'nit' en config/empresas.yaml — "
              f"ventas y soporte saldrán en 0.")

    # ── 2. Transformar (valor_ajustado, iva_ajustado, valor_bruto) ──
    df = aplicar_transformaciones(df_raw)

    # Unir NITs equivalentes (mismo tercero con DV pegado) ANTES de agrupar,
    # según config/nits_equivalentes.yaml. Solo aplica lo que el usuario curó.
    equivalencias = cargar_equivalencias(carpeta)
    df, _ = aplicar_equivalencias(df, equivalencias)

    # ── 3. Mostrar tipos disponibles y verificar la selección ──
    imprimir_tipos(df, nit, seleccion)
    verificar_seleccion(df, nit, seleccion)

    # ── 4. Guardar consolidado en processed/ ──
    ruta_proc = Path(PROCESSED) / carpeta
    ruta_proc.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta_proc / f"anual_{ANIO}.csv", index=False, encoding="utf-8-sig")
    print(f"\n  💾 Procesado guardado → processed/{carpeta}/anual_{ANIO}.csv")

    # ── 5. Reportes de revisión (NO se quitan de los totales) ──
    emisor_eq_receptor = reporte_emisor_igual_receptor(df)
    cufes_repetidos    = reporte_cufes_repetidos(df)

    # ── 6. Segmentar, agrupar y guardar informes en output/ ──
    ruta_out = Path(OUTPUT) / carpeta
    ruta_out.mkdir(parents=True, exist_ok=True)

    ventas  = extraer_ventas(df, nit, seleccion["ventas"])
    compras = extraer_compras(df, nit, seleccion["compras"])
    soporte = extraer_soporte(df, nit, seleccion["soporte"])

    inf_ventas  = informe_ventas(ventas)
    inf_compras = informe_compras(compras)
    inf_soporte = informe_soporte(soporte)

    # Posibles NITs del mismo tercero escritos de dos formas (DV pegado);
    # parten el total en dos filas. Solo se reportan, no se fusionan.
    nits_sospechosos = reporte_nits_sospechosos({
        "ventas":  (inf_ventas,  "nit_receptor", "nombre_receptor"),
        "compras": (inf_compras, "nit_emisor",   "nombre_emisor"),
        "soporte": (inf_soporte, "nit_receptor", "nombre_receptor"),
    })

    # La primera vez (sin sección para esta empresa en el YAML) se prellena
    # con los pares de mismo nombre para que el usuario los revise y, al
    # volver a correr, se apliquen. Los NO (nombre distinto) no se incluyen.
    if len(nits_sospechosos):
        pares_si = nits_sospechosos[nits_sospechosos["mismo_nombre"] == "SI"]
        asegurar_plantilla(carpeta, pares_si.to_dict("records"))

    subtotales = subtotales_por_archivo(ventas, compras, soporte)
    validacion = validacion_por_tipo(df, nit)
    # El resumen filtrado se imprime de último: es la conclusión (los totales
    # reales del entregable, ya filtrados por tipos_documento.yaml).
    resumen    = resumen_totales(ventas, compras, soporte)

    # Columnas de dinero por informe (se redondean a pesos enteros al exportar).
    MONEDA_INFORME    = ("valor_bruto", "iva_ajustado")
    MONEDA_RESUMEN    = ("valor_ajustado", "iva_ajustado", "valor_bruto")
    MONEDA_SUBTOTALES = ("valor", "iva", "valor_ajustado", "iva_ajustado", "valor_bruto")

    # Informes de análisis (entregables) → CSV con montos en pesos enteros.
    escribir_csv(inf_ventas,  ruta_out / "ventas_por_receptor.csv",    MONEDA_INFORME)
    escribir_csv(inf_compras, ruta_out / "compras_por_emisor.csv",     MONEDA_INFORME)
    escribir_csv(inf_soporte, ruta_out / "soporte_por_no_obligado.csv", MONEDA_INFORME)
    escribir_csv(resumen,     ruta_out / "resumen_totales.csv",        MONEDA_RESUMEN)
    escribir_csv(subtotales,  ruta_out / "subtotales_por_archivo.csv", MONEDA_SUBTOTALES)
    escribir_csv(validacion,  ruta_out / "validacion_por_tipo.csv",    MONEDA_INFORME)

    # Detalle (auditoría) → CSV con valores crudos (sin redondear).
    ventas.to_csv(ruta_out  / "ventas_detalle.csv",  index=False, encoding="utf-8-sig")
    compras.to_csv(ruta_out / "compras_detalle.csv", index=False, encoding="utf-8-sig")
    soporte.to_csv(ruta_out / "soporte_detalle.csv", index=False, encoding="utf-8-sig")
    if len(emisor_eq_receptor):
        emisor_eq_receptor.to_csv(ruta_out / "emisor_igual_receptor.csv", index=False, encoding="utf-8-sig")
    if len(cufes_repetidos):
        cufes_repetidos.to_csv(ruta_out / "cufes_repetidos.csv", index=False, encoding="utf-8-sig")
    if len(nits_sospechosos):
        escribir_csv(nits_sospechosos, ruta_out / "nits_sospechosos.csv",
                     ("valor_corto", "valor_largo"))
    print(f"  ✅ Informes guardados → output/{carpeta}/")


def main():
    parser = argparse.ArgumentParser(description="Pipeline de facturación electrónica (exógena).")
    parser.add_argument(
        "empresa", nargs="?", default=None,
        help="Procesar solo una empresa (por carpeta, NIT o nombre). "
             "Si se omite, procesa todas las de config/empresas.yaml.",
    )
    parser.add_argument(
        "--refrescar", action="store_true",
        help="Ignora la caché Parquet y vuelve a leer los .xlsm de origen.",
    )
    args = parser.parse_args()

    print("\n🚀 PIPELINE FACTURACIÓN ELECTRÓNICA")

    empresas = seleccionar_empresas(cargar_empresas(), args.empresa)

    for empresa in empresas:
        procesar_empresa(empresa, usar_cache=not args.refrescar)

    print(f"\n{'='*55}")
    print(f"  ✅ {len(empresas)} EMPRESA(S) PROCESADA(S)")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
