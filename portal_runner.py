# portal_runner.py
"""
FASE 2 (opcional) — Consulta el portal DIAN para enriquecer las COMPRAS.

Usa el 'ultimo_cufe' de compras_por_emisor.csv para descargar la última factura
de cada proveedor y extraer sus datos oficiales (nombre, dirección,
departamento, municipio, país).

Requiere Chrome abierto con CDP (abrir_chrome_cdp.bat) por el Cloudflare DIAN.

Pasos:
    # 1) Abre abrir_chrome_cdp.bat y pasa el captcha si aparece.
    uv run portal_runner.py descargar --empresa ruragro --cdp
    # 2) Parsea los PDFs y genera compras_terceros.csv (offline):
    uv run portal_runner.py extraer   --empresa ruragro

Sin --empresa procesa todas las del config. 'descargar' sin --all hace 2 (prueba).
"""
import sys
import argparse
from pathlib import Path

import pandas as pd

from src.empresas import cargar_empresas, seleccionar_empresas
from src.exportar import escribir_csv, escribir_excel
from src.codigos import agregar_codigos

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUTPUT = "data/output"
PORTAL = "data/portal"

COLS_DATOS = ["nombre_oficial", "direccion", "departamento", "municipio", "pais"]
COLS_CODIGO = ["codigo_departamento", "codigo_municipio", "codigo_dep_mun", "codigo_pais"]
COLS_MONTO = ["valor_bruto", "iva_ajustado", "num_documentos", "ultimo_cufe"]


def _orden_columnas() -> list[str]:
    return ["nit_emisor", "nombre_emisor"] + COLS_DATOS + COLS_CODIGO + COLS_MONTO


def _reporte_codigos(reporte: dict) -> None:
    if not any(reporte.values()):
        print("   🌎 Códigos de territorio: todo emparejado.")
        return
    print("   ⚠️  Códigos SIN match (corrige el nombre en compras_terceros.csv y corre 'codigos'):")
    for nivel in ("pais", "departamento", "municipio"):
        if reporte[nivel]:
            print(f"      {nivel}: {reporte[nivel]}")


def _rutas(carpeta: str) -> dict:
    return {
        "compras":  Path(OUTPUT) / carpeta / "compras_por_emisor.csv",
        "facturas": Path(PORTAL) / carpeta / "facturas",
        "terceros": Path(OUTPUT) / carpeta / "compras_terceros.csv",
        "codigos":  Path(OUTPUT) / carpeta / "compras_terceros_codigos.xlsx",
        "log":      Path(PORTAL) / carpeta / "descargas.csv",
    }


def _leer_compras(ruta: Path) -> pd.DataFrame:
    if not ruta.exists():
        raise FileNotFoundError(
            f"No existe {ruta}. Corre primero: uv run pipeline.py <empresa>"
        )
    df = pd.read_csv(ruta, dtype=str, encoding="utf-8-sig").fillna("")
    df.columns = df.columns.str.strip()
    for col in ("nit_emisor", "nombre_emisor", "ultimo_cufe"):
        if col not in df.columns:
            raise ValueError(f"{ruta.name} no tiene la columna '{col}'.")
    return df


def paso_descargar(carpeta: str, cdp_url: str | None, limite: int | None, headless: bool) -> None:
    from src.portal.descargar import descargar_facturas, carpeta_segura, es_pdf_valido
    import asyncio

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    rutas = _rutas(carpeta)
    df = _leer_compras(rutas["compras"])
    df = df[df["ultimo_cufe"].str.strip() != ""]
    terceros = [
        {"nit": r.nit_emisor, "nombre": r.nombre_emisor, "cufe": r.ultimo_cufe}
        for r in df.itertuples(index=False)
    ]
    if limite:
        terceros = terceros[:limite]

    print(f"\n=== DESCARGA portal DIAN — {carpeta} ({len(terceros)} terceros) ===")
    resultados = asyncio.run(
        descargar_facturas(terceros, rutas["facturas"], cdp_url=cdp_url or "", headless=headless)
    )

    rutas["log"].parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(resultados).to_csv(rutas["log"], index=False, encoding="utf-8-sig")

    # Resumen contra el filesystem (estado real e idempotente).
    faltan = []
    for r in df.itertuples(index=False):
        carp = rutas["facturas"] / carpeta_segura(r.nit_emisor or r.nombre_emisor)
        pdfs = list(carp.glob("factura_*.pdf")) if carp.exists() else []
        if not any(es_pdf_valido(p) for p in pdfs):
            faltan.append((r.nit_emisor, r.nombre_emisor))
    ok = len(df) - len(faltan)
    print(f"\n{'='*55}\nRESUMEN {carpeta}: {ok}/{len(df)} con PDF | faltan {len(faltan)}\n{'='*55}")
    for nit, nombre in faltan[:30]:
        print(f"  - {nit:15} {nombre[:40]}")
    if faltan:
        print("  (re-corre 'descargar' para reintentar; los OK se saltan)")


def paso_extraer(carpeta: str) -> None:
    from src.portal.extraer import extraer_datos_pdf

    rutas = _rutas(carpeta)
    df = _leer_compras(rutas["compras"])
    if not rutas["facturas"].exists():
        raise FileNotFoundError(
            f"No hay PDFs en {rutas['facturas']}. Corre 'descargar' primero."
        )

    from src.portal.descargar import carpeta_segura, es_pdf_valido

    datos_por_nit: dict[str, dict] = {}
    n_ok = 0
    for r in df.itertuples(index=False):
        nit = r.nit_emisor
        carp = rutas["facturas"] / carpeta_segura(nit or r.nombre_emisor)
        pdfs = sorted(p for p in carp.glob("factura_*.pdf") if es_pdf_valido(p)) if carp.exists() else []
        if not pdfs:
            continue
        try:
            d = extraer_datos_pdf(pdfs[0])
            datos_por_nit[nit] = {
                "nombre_oficial": d.get("Razón Social", ""),
                "direccion":      d.get("Dirección", ""),
                "departamento":   d.get("Departamento", ""),
                "municipio":      d.get("Municipio / Ciudad", ""),
                "pais":           d.get("País", ""),
            }
            n_ok += 1
        except Exception as e:
            print(f"  ⚠️  {nit}: error parseando PDF: {str(e)[:80]}")

    for col in COLS_DATOS:
        df[col] = df["nit_emisor"].map(lambda n: datos_por_nit.get(n, {}).get(col, ""))

    # Reordenar: identidad + datos del portal, luego montos.
    orden = (["nit_emisor", "nombre_emisor"] + COLS_DATOS
             + ["valor_bruto", "iva_ajustado", "num_documentos", "ultimo_cufe"])
    df = df[[c for c in orden if c in df.columns]]

    escribir_csv(df, rutas["terceros"], cols_moneda=("valor_bruto", "iva_ajustado"))
    print(f"\n✅ {carpeta}: {n_ok}/{len(df)} terceros con datos del portal")
    print(f"   Guardado → {rutas['terceros']}")


def paso_codigos(carpeta: str) -> None:
    """
    Asigna códigos DIAN (país/departamento/municipio) leyendo compras_terceros.csv
    y escribe un archivo NUEVO (compras_terceros_codigos.csv) — no toca el original,
    para poder validar la normalización. Re-ejecutable tras corregir nombres a mano.
    """
    rutas = _rutas(carpeta)
    if not rutas["terceros"].exists():
        raise FileNotFoundError(f"No existe {rutas['terceros']}. Corre 'extraer' primero.")

    df = pd.read_csv(rutas["terceros"], dtype=str, encoding="utf-8-sig").fillna("")
    df, reporte = agregar_codigos(df)
    df = df[[c for c in _orden_columnas() if c in df.columns]]

    # .xlsx con códigos/NIT/CUFE como TEXTO → Excel muestra '001', no 1.
    escribir_excel(
        df, rutas["codigos"],
        cols_texto=("nit_emisor",) + tuple(COLS_CODIGO) + ("ultimo_cufe",),
        cols_moneda=("valor_bruto", "iva_ajustado"),
    )
    con_muni = int((df["codigo_municipio"].astype(str).str.strip() != "").sum())
    print(f"\n✅ {carpeta}: códigos de municipio asignados a {con_muni} filas")
    print(f"   Guardado → {rutas['codigos']}  (compras_terceros.csv quedó intacto)")
    _reporte_codigos(reporte)


def main():
    ap = argparse.ArgumentParser(description="Consulta el portal DIAN para enriquecer las compras.")
    ap.add_argument("paso", choices=["descargar", "extraer", "codigos"], help="Qué hacer")
    ap.add_argument("--empresa", default=None, help="Solo una empresa (carpeta/NIT/nombre). Si se omite, todas.")
    ap.add_argument("--all", action="store_true", help="(descargar) Procesar todos los terceros (default: 2)")
    ap.add_argument("--limite", type=int, default=2, help="(descargar) Cuántos terceros procesar")
    ap.add_argument("--headless", action="store_true", help="(descargar sin --cdp) Sin ventana")
    ap.add_argument("--cdp", nargs="?", const="http://localhost:9222", default=None,
                    help="Conectar a Chrome existente (default: http://localhost:9222)")
    args = ap.parse_args()

    empresas = seleccionar_empresas(cargar_empresas(), args.empresa)
    limite = None if args.all else args.limite

    for emp in empresas:
        carpeta = emp["carpeta"]
        if args.paso == "descargar":
            paso_descargar(carpeta, args.cdp, limite, args.headless)
        elif args.paso == "extraer":
            paso_extraer(carpeta)
        else:
            paso_codigos(carpeta)


if __name__ == "__main__":
    main()
