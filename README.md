# Pipeline Facturación Electrónica — Información Exógena

Pipeline ETL que toma los reportes de **compras y ventas DIAN** (facturación
electrónica) de una empresa, los consolida, ajusta las notas crédito y genera
los informes agrupados por tercero que se necesitan para la **información
exógena**.

---

## ¿Qué hace?

1. **Carga** todos los archivos Excel (`.xlsm`/`.xlsx`) de cada empresa, detectando
   automáticamente la hoja de datos y unificando los nombres de columna.
2. **Transforma**: a las notas crédito les pone el valor y el IVA en negativo y
   calcula el valor bruto.

   | Columna | Cálculo |
   |---|---|
   | `valor_ajustado` | `valor` (negativo si es nota crédito) |
   | `iva_ajustado` | `iva` (negativo si es nota crédito) |
   | `valor_bruto` | `valor_ajustado − iva_ajustado` |

   > Los archivos de origen ya traen estas columnas calculadas a mano; el pipeline
   > las **ignora** y las recalcula por código.

3. **Segmenta** y genera los **informes agrupados por tercero**.

   | Informe | Filtro | Agrupado por |
   |---|---|---|
   | **Ventas** | `nit_emisor == NIT de la empresa` | `nit_receptor` (a quién se le vendió) |
   | **Compras** | `nit_emisor != NIT de la empresa` | `nit_emisor` (a quién se le compró) |
   | **Documento soporte** | `nit_emisor == NIT de la empresa`, solo documentos soporte con no obligados | `nit_receptor` (el no obligado) |

   Cada informe suma `valor_bruto` e `iva_ajustado` por NIT, y solo incluye los
   tipos de documento seleccionados para ese informe (ver más abajo).

---

## Requisitos

- [uv](https://docs.astral.sh/uv/) (gestor de entornos/dependencias de Python)
- Python ≥ 3.14 (uv lo instala según `.python-version`)
- Solo para la FASE 2 (portal DIAN): **Google Chrome** instalado.

## Instalación (primera vez)

Desde la carpeta del proyecto, en PowerShell:

```powershell
uv sync
```

Eso crea el entorno e instala todas las dependencias (`pandas`, `openpyxl`,
`pyyaml`, `pyarrow`, y para la FASE 2 `playwright`, `pypdf`). No necesitas
activar nada: todo se corre con `uv run <script>`.

> No hace falta `playwright install chromium`: la FASE 2 se conecta a tu Chrome
> real (ver esa sección).

---

## Estructura de carpetas

```
pipeline/
├─ config/
│  ├─ empresas.yaml            # empresas a procesar (nombre, nit, carpeta)
│  ├─ tipos_documento.yaml     # tipos de documento por informe (default + por empresa)
│  └─ nits_equivalentes.yaml   # unir NITs del mismo tercero (DV pegado) — se prellena solo
├─ data/
│  ├─ raw/<carpeta>/*.xlsm     # archivos de entrada por empresa  ← LOS PONES TÚ
│  ├─ cache/<carpeta>.parquet  # caché de lectura de los Excel (generado)
│  ├─ processed/<carpeta>/     # consolidado anual (generado)
│  ├─ output/<carpeta>/        # informes finales (generado)
│  ├─ portal/<carpeta>/        # PDFs descargados del portal — FASE 2 (generado)
│  └─ perfil/<carpeta>.html    # reportes HTML de exploración (generado)
├─ src/                        # módulos del pipeline (incl. src/portal/ para FASE 2)
├─ ingestar.py                 # FASE 0: lee los Excel y arma el caché Parquet
├─ discovery_runner.py         # inspecciona columnas de los archivos
├─ tipos_runner.py             # lista los tipos de documento presentes
├─ pipeline.py                 # FASE 1: ejecuta el proceso completo
├─ portal_runner.py            # FASE 2: descarga y parsea facturas del portal DIAN
├─ perfil_html.py              # genera reportes HTML de exploración (entorno aparte)
└─ abrir_chrome_cdp.bat        # FASE 2: abre Chrome para el portal
```

Todo lo de `data/` salvo `raw/` es generado y se puede borrar para re-correr.

---

## Uso

### 1. Coloca los archivos de entrada

Crea una subcarpeta por empresa dentro de `data/raw/` y deja ahí sus Excel
(`.xlsm`/`.xlsx`) de compras y ventas DIAN del año:

```
data/raw/ruragro/COMPRAS Y VENTAS DIAN ... 2025.xlsm
```

El nombre de la subcarpeta (`ruragro`) es el que usarás como `carpeta` en el
config. Puede haber varios archivos por empresa (trimestrales, cuatrimestrales,
lo que sea): el pipeline los toma todos.

### 2. Configura las empresas

Edita `config/empresas.yaml`. El `nit` debe ser el **número** de NIT de la
empresa (sin dígito de verificación), y `carpeta` el nombre exacto de la
subcarpeta del paso 1:

```yaml
empresas:
  - nombre: "RURAGRO S.A.S."
    nit: "901093775"
    carpeta: "ruragro"
```

### 3. Ingesta a Parquet (una sola vez)

Leer los `.xlsm` es lo lento del proceso. Conviértelos al caché Parquet **una
vez** al inicio; a partir de ahí todo lo demás (ver tipos, ejecutar) lee del
caché en segundos:

```powershell
uv run ingestar.py            # todas las empresas
uv run ingestar.py ruragro    # solo una
```

Esto crea `data/cache/<carpeta>.parquet`. El caché se invalida solo si cambias
un `.xlsm`; usa `--refrescar` para forzar la relectura.

### 4. Mira qué tipos de documento hay en los datos

```powershell
uv run tipos_runner.py ruragro
```

Muestra, por ventas y por compras, todos los tipos de documento presentes con
su conteo, marcando con ✅ los que están seleccionados actualmente. (Sin el
nombre de empresa, las recorre todas.) Lee del caché → es instantáneo.

### 5. Elige los tipos de documento

Edita `config/tipos_documento.yaml` con los tipos que quieras incluir en cada
lado. Normalmente son factura electrónica y nota de crédito; agrega otros si los
necesitas (las tildes y mayúsculas no importan).

La selección es **por empresa**: hay un bloque `default` que aplica a todas, y
puedes sobrescribirlo para una empresa usando su `carpeta` como clave. Una
empresa solo cambia las listas que define; el resto las hereda del `default`.

```yaml
default:                       # se usa para cualquier empresa sin override
  ventas:
    - "Factura electrónica"
    - "Nota de crédito electrónica"
  compras:
    - "Factura electrónica"
    - "Nota de crédito electrónica"
  soporte:
    - "Documento soporte con no obligados"

ruragro:                       # override solo para RURAGRO
  compras:
    - "Factura electrónica"
    - "Nota de crédito electrónica"
    - "Documento equivalente POS"
```

Hay tres listas: `ventas` y `soporte` son documentos donde la empresa es el
emisor; `compras` son documentos emitidos por un tercero. Si configuras un tipo
que no existe en los datos de la empresa, el pipeline lo avisa al correr.

### 6. (Opcional) Revisar las columnas de los archivos

```powershell
uv run discovery_runner.py ruragro
```

Reporta la hoja de datos detectada, cómo se mapea cada columna cruda al nombre
estándar y avisa de columnas "SIN MAPEAR".

### 7. Ejecutar el pipeline

```powershell
uv run pipeline.py            # procesa TODAS las empresas del config
uv run pipeline.py ruragro    # procesa SOLO una empresa
uv run pipeline.py ruragro --refrescar   # ignora la caché y relee los .xlsm
```

Para procesar una sola empresa, pásala como argumento. El filtro acepta la
`carpeta`, el `nit` o parte del `nombre` (ignora mayúsculas). Mismo argumento
disponible en `tipos_runner.py` y `discovery_runner.py`.

Al terminar, en consola sale el **RESUMEN DE TOTALES** y los **subtotales por
archivo** para cuadrar de un vistazo; los archivos quedan en
`data/output/<carpeta>/` (ver [Resultados](#resultados)). Si tienes cifras de
control, compáralas contra `resumen_totales.csv` y `subtotales_por_archivo.csv`.

**Caché:** lee del Parquet creado en el paso 3 (segundos). Si te saltaste la
ingesta, la primera corrida la construye sola (más lenta). Cambiar
`config/tipos_documento.yaml` NO requiere refrescar el caché (guarda los datos
crudos, antes de filtrar por tipo); usa `--refrescar` solo si cambió un `.xlsm`.

### 8. (Opcional) Unir NITs del mismo tercero

A veces un mismo tercero llega escrito con **dos NITs distintos** y el informe lo
parte en dos filas. Lo más común es que en unas facturas le **peguen el dígito de
verificación al final, sin guion** (p. ej. `9016550371` en vez de `901655037`);
también pasa por errores de digitación. El pipeline lo detecta y, si quieres,
lo consolida en una sola fila con el total sumado.

Es un flujo de **dos pasadas**:

1. **Primera corrida** (`uv run pipeline.py <empresa>`): detecta los pares
   sospechosos, los lista en `nits_sospechosos.csv` y **prellena**
   `config/nits_equivalentes.yaml` con los que tienen el **mismo nombre** (los más
   probables). Te avisa en consola: *"Plantilla creada… revísala y vuelve a correr"*.

2. **Revisa** `config/nits_equivalentes.yaml`. El formato es `NIT a corregir → NIT
   correcto` (el correcto es el **canónico, sin dígito de verificación**, que es el
   que pide la DIAN):

   ```yaml
   ruragro_ventas:
     "9016550371": "901655037"    # ECOGLOBAL ELIM SAS   ← se unen en el de la derecha
     "183998122":  "18399812"     # JOVANNY RUBIANO LOPEZ
   default:                        # (opcional) aplica a todas las empresas
     "22222222": "222222222222"   # CONSUMIDOR FINAL
   ```

   - **Borra** la línea de cualquier par que NO debas unir.
   - **Agrega a mano** los que el detector no encuentra (los typos, p. ej. un
     dígito cambiado en el medio: `"1052389457": "1052389467"`).

3. **Vuelve a correr** el pipeline: ahora el informe sale **consolidado** (ECOGLOBAL
   pasa de 2 filas a 1, sumando valores y nº de documentos).

> **Solo se une lo que esté en el YAML** — nunca a ciegas. Los pares con nombre
> **distinto** (otro contribuyente cuyo NIT coincide por azar) NO se prellenan; se
> quedan en `nits_sospechosos.csv` para que decidas tú. Una vez que la empresa
> tiene su sección en el archivo, el pipeline la **respeta tal cual** (no la
> vuelve a sobrescribir). Editar este YAML **no** requiere `--refrescar`.

---

## Resultados

Por cada empresa, en `data/output/<carpeta>/`:

| Archivo | Contenido |
|---|---|
| `ventas_por_receptor.csv` | **Informe de ventas** agrupado por NIT receptor |
| `compras_por_emisor.csv` | **Informe de compras** agrupado por NIT emisor. Incluye `ultimo_cufe` (factura más reciente de cada emisor) para buscarla en el portal DIAN |
| `soporte_por_no_obligado.csv` | **Informe de documento soporte** agrupado por NIT del no obligado |
| `resumen_totales.csv` | **Totales comparativos** (documentos, terceros, valor y IVA) de los tres informes |
| `subtotales_por_archivo.csv` | Subtotales por **archivo × informe × tipo de documento** (verificación) |
| `validacion_por_tipo.csv` | Por lado (ventas/compras) y **cada tipo de documento** (sin filtrar): nº de terceros y total, más el total de terceros únicos. Para validar cuántos terceros hay y decidir qué tipos incluir |
| `emisor_igual_receptor.csv` | Registros con `nit_emisor == nit_receptor` (con sus valores). Pueden ser legítimos (p. ej. la estación tanquea su propio vehículo) o un NIT mal digitado. Solo se **reportan**; su valor **sigue sumando** en los totales |
| `cufes_repetidos.csv` | Documentos cuyo **CUFE aparece más de una vez** (el CUFE es único → fila cargada dos veces). Ordenado por CUFE para revisarlos; no se quitan de los totales |
| `nits_sospechosos.csv` | Pares de NIT que parecen el **mismo tercero** escrito de dos formas (uno = el otro + un dígito final, típicamente el de verificación pegado). La columna `mismo_nombre` (SI/NO) distingue un duplicado real de una coincidencia. Para consolidarlos, ver el [paso 8](#8-opcional-unir-nits-del-mismo-tercero). Solo se reporta; no cambia los totales por sí solo |
| `ventas_detalle.csv` | Registros de ventas filtrados (auditoría) |
| `compras_detalle.csv` | Registros de compras filtrados (auditoría) |
| `soporte_detalle.csv` | Registros de documento soporte filtrados (auditoría) |

Y en `data/processed/<carpeta>/anual_<año>.csv` queda el consolidado completo
con las columnas ajustadas, antes de segmentar.

### Formato de los CSV

- Los **informes de análisis** (`*_por_*.csv`, `resumen_totales`, `subtotales_por_archivo`,
  `validacion_por_tipo`) traen los **montos en pesos enteros** (como los pide la DIAN)
  y los **nombres sin espacios sobrantes**. Al no tener decimales, los números se
  leen igual en Excel (es-CO) y en Google Sheets, sin líos de separador decimal.
- Los **detalle** (`*_detalle.csv`) conservan los **valores crudos con decimales**
  (sirven de auditoría/respaldo, no para reportar).
- Todos los CSV se guardan con BOM UTF-8 para que Excel respete tildes y ñ.

---

## Exploración del dataset (opcional)

Para revisar un conjunto de datos a fondo (tipos, nulos, distribuciones,
duplicados) hay dos vías. Las librerías de "reporte automático" tipo
`ydata-profiling` / `fg-data-profiling` **no se instalan en el entorno del
proyecto** porque arrastran `numba`/`llvmlite`, que aún no tienen versiones
compatibles con Python 3.14. Por eso la exploración va por fuera del entorno
principal.

### A) Exploración con pandas — rápida, sin instalar nada

`src/explorar.py` perfila cualquier DataFrame o caché con solo pandas. Da
resumen general, tabla por columna (tipo/nulos/únicos/ejemplos), fechas por mes,
montos (suma/promedio/mín/máx/negativos) y chequeos propios de exógena (CUFE
repetidos, `emisor == receptor`, notas de crédito).

```powershell
uv run python -m src.explorar ruragro_ventas   # perfila un caché del cache/
```

Desde un notebook o script:

```python
from src.explorar import perfilar, cargar_cache, resumen_columnas
df = cargar_cache("ruragro_ventas")   # lee data/cache/<nombre>.parquet
perfilar(df)                          # imprime el perfil completo
resumen_columnas(df)                  # detalle por columna como DataFrame
```

El notebook `notebooks/notbook.ipynb` ya trae celdas que llaman a esto.

### B) Reporte HTML (ydata-profiling) — en un entorno aparte

Como `ydata-profiling` no corre en Python 3.14, se instala en un entorno
separado con Python 3.12. Creación (una sola vez):

```powershell
uv venv --python 3.12 .venv-profiling
uv pip install --python .venv-profiling/Scripts/python.exe ydata-profiling "setuptools<80" pyarrow
```

> `setuptools<80` es necesario porque `ydata-profiling` aún usa `pkg_resources`,
> que las versiones nuevas de setuptools ya quitaron; `pyarrow` para leer los
> caché Parquet.

`perfil_html.py` lee `data/cache/<nombre>.parquet` y escribe
`data/perfil/<nombre>.html`. **Se corre con el Python del entorno aparte, no con
`uv run`:**

```powershell
.venv-profiling\Scripts\python.exe perfil_html.py ruragro_ventas   # un caché
.venv-profiling\Scripts\python.exe perfil_html.py                  # todos
```

Abre el `.html` resultante en el navegador. Usa `minimal=True` (rápido en los
caché grandes); edita `perfil_html.py` si quieres correlaciones/interacciones
completas.

---

## FASE 2 (opcional) — Enriquecer compras desde el portal DIAN

Para las **compras** necesitamos el **nombre oficial y la dirección** de cada
proveedor, que no vienen en los Excel. Esta fase usa el `ultimo_cufe` de
`compras_por_emisor.csv` para descargar la última factura de cada proveedor del
portal DIAN y parsear sus datos. (Las ventas no la necesitan: los nombres ya
están en tus datos.)

> Requiere **Google Chrome** instalado. El portal usa Cloudflare, así que hay
> que conectarse a un Chrome real abierto a mano (no sirve headless).

```powershell
# 1) Abrir Chrome con depuración remota (NO cerrar esta ventana).
#    Si Cloudflare muestra captcha, márcalo y espera el chulo verde.
#    En PowerShell hay que anteponer .\ para correr el .bat de la carpeta actual.
.\abrir_chrome_cdp.bat

# 2) Descargar las facturas (prueba con 2; agrega --all para todas).
uv run portal_runner.py descargar --empresa ruragro --cdp --all

# 3) Parsear los PDFs y generar el CSV enriquecido (offline).
uv run portal_runner.py extraer --empresa ruragro

# 4) Asignar códigos DIAN de país/departamento/municipio (offline).
uv run portal_runner.py codigos --empresa ruragro
```

Salidas:
- `data/portal/<empresa>/facturas/<NIT>/factura_*.pdf` — PDFs descargados (idempotente: re-correr salta los que ya están).
- `data/output/<empresa>/compras_terceros.csv` — `compras_por_emisor` + `nombre_oficial`, `direccion`, `departamento`, `municipio`, `pais`.
- `data/output/<empresa>/compras_terceros_codigos.xlsx` — lo anterior **+ códigos** (`codigo_departamento`, `codigo_municipio`, `codigo_dep_mun`, `codigo_pais`). Es `.xlsx` (no CSV) a propósito: guarda los códigos como **texto** para que Excel muestre `001` y `08`, no `1` y `8`.

`descargar` es reanudable: si Cloudflare corta, vuelve a correrlo y continúa donde quedó. Sin `--empresa` procesa todas.

### Sobre los códigos de territorio (paso 4)

Los nombres del PDF vienen muy inconsistentes (`Colombia`/`COLOMBIA`, `Bogotá D.C.`/`BOGOTÁ, D. C.`, etc.). El paso `codigos` normaliza (sin tildes/mayúsculas/puntuación), trata todas las variantes de Bogotá como `11`, y **busca el municipio dentro de su departamento** (clave, porque hay municipios homónimos: *Armenia* es `63001` en Quindío pero `05055` en Antioquia).

- **No sobrescribe** `compras_terceros.csv`: escribe un archivo aparte (`.xlsx`), para que valides la normalización comparando ambos. El `.xlsx` conserva los ceros a la izquierda de los códigos (`001`, `05`).
- Lo que **no logre emparejar** lo lista en consola (p. ej. un municipio puesto por error en el campo departamento). Corrige ese nombre en `compras_terceros.csv` y vuelve a correr `codigos` — es re-ejecutable.
- Fuente de códigos: `data/codigos.csv`.

## Notas

- El año a procesar se define con `ANIO` en `pipeline.py`.
- Una venta a "Consumidor Final" suele venir con el NIT genérico `222222222222`.
- Si un mismo NIT aparece con varios nombres, el informe usa el nombre más
  frecuente.
- Si un mismo tercero aparece con **varios NITs** (p. ej. el dígito de verificación
  pegado), se consolida con `config/nits_equivalentes.yaml` (ver
  [paso 8](#8-opcional-unir-nits-del-mismo-tercero)).
