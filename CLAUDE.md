# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

ETL pipeline for Colombian DIAN electronic-invoicing data (compras y ventas), used to prepare **información exógena** tax reporting. It consolidates a company's periodic invoice exports, adjusts credit notes, and segments the result into per-company `ventas.csv` / `compras.csv`.

The codebase and all naming are in **Spanish** — keep new identifiers, comments, and console output in Spanish to match.

## Commands

The project uses `uv` (note `.python-version`, `pyproject.toml`, `requires-python >=3.14`).

```bash
uv run ingestar.py           # FASE 0: read .xlsm once → build data/cache/<empresa>.parquet (the slow step, front-loaded)
uv run discovery_runner.py   # inspect raw .xlsm: detected data sheet, raw→canonical column map, consistency across periods
uv run tipos_runner.py       # list which tipo_documento values exist (per ventas/compras side); reads cache → instant
uv run pipeline.py           # main run — load → transform → filter by tipo → segment → grouped informes
```

Recommended order: `ingestar` (once) → `tipos_runner` → edit `tipos_documento.yaml` → `pipeline`. Ingest is just an explicit, well-named call to `cargar_periodos_empresa`; `tipos_runner`/`pipeline` build the cache on first use anyway, but front-loading it makes everything after fast.

All three runners take an optional positional arg to process a single company (matched by `carpeta`, `nit`, or substring of `nombre`), e.g. `uv run pipeline.py ruragro`. Omit it to process every company in `config/empresas.yaml`. Selection is shared via `src/empresas.py` (`cargar_empresas` + `seleccionar_empresas`).

Dependencies are declared in `pyproject.toml` (and mirrored in `requirements.txt`): `pandas`, `openpyxl`, `pyyaml`. `main.py` is a placeholder — the real entrypoint is `pipeline.py`. There are no tests or linter config.

Both entrypoints call `sys.stdout.reconfigure(encoding="utf-8")` because the console output is emoji/accent-heavy and the default Windows cp1252 console aborts on it. Keep that line when adding new entrypoints.

## Architecture

Two-phase design. Phase 1 (discovery) is a non-interactive diagnostic to confirm the column mapping covers a data source; phase 2 (pipeline) is the repeatable processing run.

```
src/mapping.py                 normalizar() + MAPA_COLUMNAS (raw DIAN → canonical) + COLUMNAS_OMITIR + COLUMNAS_REQUERIDAS
src/tipos.py                   load/report/filter tipo_documento selection (config/tipos_documento.yaml)
discovery_runner.py → src/discovery.py    per-file report of detected sheet, raw→canonical map, "SIN MAPEAR" warnings
tipos_runner.py     → src/tipos.py         standalone "which document types exist" report
pipeline.py         → src/loader.py        glob .xlsm in company folder, autodetect data sheet, map columns, concat
                      src/transformer.py   valor_ajustado / iva_ajustado (NC → negative) + valor_bruto = ajustado − ajustado
                      src/equivalencias.py unir NITs del mismo tercero (DV pegado) antes de agrupar (config/nits_equivalentes.yaml)
                      src/tipos.py          filter rows to the configured tipo_documento per side
                      src/segmentador.py    extraer_ventas/compras (split) + informe_ventas/compras (group by counterpart NIT)
```

Data flow: `data/raw/<carpeta>/*.xlsm` → loader concatenates all periods → transformer adds adjusted columns → `data/processed/<carpeta>/anual_<ANIO>.csv` → filter by tipo + segment + group → `data/output/<carpeta>/`. Both entrypoints are driven by **`config/empresas.yaml`** (list under `empresas`, each `nombre`/`nit`/`carpeta`); per-company config is the unit of iteration.

### Exógena reporting logic (the core domain rules)

- Three informes, each a filter + group-by on the same transformed DataFrame:
  - **Ventas** = `nit_emisor == NIT_empresa`, grouped by `nit_receptor`.
  - **Compras** = `nit_emisor != NIT_empresa` (company removed from the emisor side; the supplier is the emisor — *not* `nit_receptor == empresa`), grouped by `nit_emisor`.
  - **Documento soporte** = `nit_emisor == NIT_empresa` (same emisor side as ventas) but selecting only `Documento soporte con no obligados`, grouped by `nit_receptor` (the no-obligado). This dataset is the company's own DIAN export, so "emitted by us" vs "emitted by a third party" is the split.
- Each informe is filtered to the **document types selected per informe** in `config/tipos_documento.yaml` (keys `ventas`/`compras`/`soporte`; normally `Factura electrónica` + `Nota de crédito electrónica`; editable without touching code). Selection is **per company**: a `default` block applies to all, and a top-level key matching a company's `carpeta` overrides it per-list (company > default > internal fallback). `cargar_seleccion(carpeta)` resolves this; it also accepts the old flat format (top-level `ventas`/`compras`/`soporte` treated as the default). In `src/tipos.py`, `LADO_EMISOR_EMPRESA`/`LADO_EMISOR_TERCERO` declare which side each key belongs to, and `verificar_seleccion` warns when a configured type is absent from that company's data. `tipos_runner.py` / the pipeline header print the available types so the user can decide.
- **Adjusted values** (`src/transformer.py`): credit notes get `valor`/`iva` forced negative → `valor_ajustado`, `iva_ajustado`; `valor_bruto = valor_ajustado − iva_ajustado`. The source ships these pre-computed by hand — they are dropped and recomputed.
- **CSV formatting** (`src/exportar.py`, `escribir_csv`): analysis reports are written with money columns rounded to **integer pesos** (DIAN format; round-half-away-from-zero via `a_entero`, preserving NC negatives) and text columns whitespace-collapsed. Integer money sidesteps the `.`-vs-`,` decimal-separator problem across Excel-CO/Sheets. The `*_detalle.csv` files keep raw decimal values (audit); they use plain `to_csv`, not `escribir_csv`.
- **Review reports — flag, never drop** (values always stay in the totals): `reporte_emisor_igual_receptor` → `emisor_igual_receptor.csv` (rows with `nit_emisor == nit_receptor`; may be legit, e.g. a gas station fueling its own vehicle, or a miskeyed NIT — review only). `reporte_cufes_repetidos` → `cufes_repetidos.csv` (CUFE/CUDE appearing >1× = a row loaded twice; CUFE is globally unique). Both are computed on the full `df` and kept in the informes because the user's verified totals include them; the pipeline does not deduplicate. `reporte_nits_sospechosos` → `nits_sospechosos.csv` (only written when pairs exist): within each informe, flags pairs where one NIT equals another NIT + a trailing digit — the **verification digit (DV) glued without a hyphen** (`901655037` vs `9016550371`), which splits one tercero's total across two grouped rows. `mismo_nombre` (`SI`/`NO`, via `_mismo_tercero` substring match on accent/punct-stripped names) distinguishes a real DV-glued duplicate from a coincidence (`901974152` VOLTIX vs `9019741529` LUZ FELIPE PEREZ — a *different* taxpayer whose NIT happens to be VOLTIX+1 digit). **Flag only — never auto-merge automatically**; stripping the trailing digit blindly would merge distinct taxpayers. The merge is opt-in via the config below.
- **NIT equivalences (`src/equivalencias.py`, opt-in consolidation)**: to actually consolidate a split tercero, the user curates `config/nits_equivalentes.yaml` — a per-company (`carpeta`) + optional `default` map of `"nit_a_corregir": "nit_correcto"` (canonical = WITHOUT verification digit, as DIAN wants). `aplicar_equivalencias` rewrites `nit_emisor`/`nit_receptor` on the full transformed `df` **before** segmentation, so the `groupby` consolidates the rows and `valor`/`num_documentos`/`ultimo_cufe` recompute correctly (names untouched — `_nombre_representativo` picks the most frequent). It applies ONLY what is in the file — never a heuristic. **Two-pass workflow**: 1st `pipeline.py` run detects the `mismo_nombre=SI` pairs and `asegurar_plantilla` pre-fills the company section in the YAML (only if absent — an existing section is respected, never clobbered) then prints "revísala y vuelve a correr"; the user reviews (removes false merges, adds typos the detector can't find like a mid-NIT digit change or `CONSUMIDOR FINAL`), and the 2nd run applies it. The `NO` pairs (different names, e.g. VOLTIX vs LUZ FELIPE) are never pre-filled. Equivalences apply at the pipeline layer, NOT the parquet cache, so editing the YAML takes effect WITHOUT `--refrescar`.
- **`compras_por_emisor.csv`** also carries `ultimo_cufe` (`_agrupar(..., con_ultimo_cufe=True)` → `_ultimo_cufe_por_nit`): the CUFE of each supplier's most recent invoice (by `fecha_emision`, dayfirst). This is the bridge to the `busqueda_portal/` scraper, whose `historico.csv` needs `CUFE/CUDE` + `NIT Emisor` + `Nombre Emisor`.
- **Outputs** per company (`src/segmentador.py`, each summing `valor_bruto` + `iva_ajustado`): `{ventas,compras,soporte}_detalle.csv` (filtered rows, audit), `ventas_por_receptor.csv` / `compras_por_emisor.csv` / `soporte_por_no_obligado.csv` (deliverable informes), `resumen_totales.csv` (`resumen_totales()` — one row per informe), `subtotales_por_archivo.csv` (`subtotales_por_archivo()` — breakdown by archivo × informe × tipo_documento with valor/iva/valor_ajustado/iva_ajustado/valor_bruto, for cross-checking against source pivots), `validacion_por_tipo.csv` (`validacion_por_tipo()` — per ventas/compras side, every tipo_documento UNFILTERED with terceros count + totals + a unique-terceros total row; used to validate counts and decide which types to include), `nits_sospechosos.csv` (when present — see review reports above), and `inconsistencias.csv` when present.

### Column mapping — the central contract

The raw DIAN export has 35 Spanish, accented column names; the rest of the pipeline works on canonical snake_case names (`tipo_documento`, `nit_emisor`, `nit_receptor`, `valor`, `iva`, ...). `src/mapping.py` is the single source of truth:
- `normalizar()` strips accents/case/whitespace, so matching is robust to per-file encoding differences. **Match on normalized names, never raw.**
- `MAPA_COLUMNAS` maps normalized → canonical. Note `total` → **`valor`** (the document total is the base the transformer works on).
- `COLUMNAS_OMITIR` = `valor ajustado`, `iva ajustado`, `valor bruto`. The source file ships these pre-computed **by hand**; the pipeline deliberately drops them and recomputes from `valor`/`iva` so the logic lives in code.
- To support a new raw column, add it to `MAPA_COLUMNAS`. Discovery flags anything unmapped as "SIN MAPEAR".

### Performance / caching

Reading `.xlsm` via openpyxl is the dominant cost (~5 min for 360k rows × 3 files). `cargar_periodos_empresa` caches the consolidated, column-mapped DataFrame to `data/cache/<carpeta>.parquet` and reads from it when the cache is newer than every source Excel (~16× faster: ~325s → ~20s). The cache holds the **raw mapped data before type filtering**, so editing `config/tipos_documento.yaml` does NOT require invalidation — only a changed source file (auto-detected via mtime) or changed load/mapping logic (`pipeline.py --refrescar`, i.e. `usar_cache=False`). Parquet also preserves dtypes, avoiding the NIT-as-float issue on reload. Requires `pyarrow`.

### Data-source specifics (RURAGRO)

- The real data sheet is named `Rp_Doc_*` (name varies per file); sibling sheets (`DOCS` empty, `VENTAS NIT` manual) must be skipped. The loader/discovery **autodetect** the sheet by checking for required columns — do not hardcode a sheet name.
- Credit notes are detected by normalized `tipo_documento` containing `"nota de credito"` (excludes débito). They arrive positive in the source and are negated in code.
- Files are **cuatrimestral** (ene-abr / may-ago / sep-dic), not quarterly. The loader globs all Excel files in the folder, so period count/naming doesn't matter. (HOYOS is trimestral — 4 files; still fine.)

## Phase 2 — DIAN portal enrichment (optional, separate runner)

`portal_runner.py` enriches **compras** with official supplier name + address (not present in the Excels). Intentionally NOT part of `pipeline.py`: it needs a manually-opened Chrome (Cloudflare blocks headless/Playwright-launched), is slow (one PDF per supplier), and runs after `pipeline.py` produced `compras_por_emisor.csv`. `busqueda_portal/` is the original standalone tool, kept as reference; `src/portal/` is the reimplementation integrated here.

- `src/portal/descargar.py` — download a PDF by CUFE via Playwright over CDP to a real Chrome (`abrir_chrome_cdp.bat`, port 9222). Handles Cloudflare Turnstile + "falta token" retries; idempotent (skips valid existing PDFs). Lazy-imported so the `extraer` step stays offline (only needs pypdf).
- `src/portal/extraer.py` — parse "Datos del Emisor" of the PDF's 1st page (regex over known DIAN labels) → razón social, dirección, departamento, municipio, país.
- `src/codigos.py` (`agregar_codigos`) — assigns DIAN país/departamento/municipio codes from `data/codigos.csv` (three stacked lists: deptos, municipios keyed by `Codigo dep-mun`, países). Aggressive normalization (`_norm`: strip accents/case/punctuation), Bogotá special-cased to `11`/`11001` (covers all variants incl. the `Bogot�` mojibake), and **municipio matched within its department** (homonyms: *Armenia* = 63001 Quindío vs 05055 Antioquia). Returns `(df, reporte)` where `reporte` lists names it could NOT match — surfaced, never silently blanked or guessed.
- Flow: `compras_por_emisor.csv` (`ultimo_cufe`) → `data/portal/<carpeta>/facturas/<NIT>/` → `compras_terceros.csv` (portal data) → `compras_terceros_codigos.xlsx` (+ codes, a SEPARATE file so the user validates the normalization; never overwrites `compras_terceros.csv`). It is **`.xlsx`** (via `escribir_excel`, not `escribir_csv`) on purpose: codes have leading zeros (`001`, `05`) that Excel strips from a CSV — xlsx stores them as text cells (`number_format="@"`), money stays integer `#,##0`.
- Commands: `descargar --empresa <x> --cdp [--all]` → `extraer --empresa <x>` → `codigos --empresa <x>`. The `codigos` step is offline and re-runnable (fix a bad name in `compras_terceros.csv`, re-run). Only compras use the portal; ventas names come from our own data.
