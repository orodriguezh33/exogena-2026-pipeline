# src/portal/descargar.py
"""
Descarga el PDF de una factura del portal público DIAN, dado su CUFE/CUDE.

Se conecta a un Chrome real abierto con depuración remota (CDP) — ver
abrir_chrome_cdp.bat — porque Cloudflare bloquea un navegador lanzado por
Playwright directamente. Maneja el Turnstile de Cloudflare y los reintentos
de "falta token". Es idempotente: si el PDF ya existe y es válido, lo salta.

Lógica de descarga adaptada de busqueda_portal/facturas.py.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from playwright.async_api import TimeoutError as PWTimeoutError, async_playwright

DIAN_URL = "https://catalogo-vpfe.dian.gov.co/User/SearchDocument?documentKey={cufe}"


def _is_pdf(data: bytes) -> bool:
    return len(data) >= 5 and data[:5] == b"%PDF-"


def carpeta_segura(name: str) -> str:
    name = (name or "sin_nit").strip()
    return re.sub(r'[<>:"/\\|?*]+', "_", name) or "sin_nit"


def es_pdf_valido(p: Path) -> bool:
    """True si existe, pesa >5KB y empieza con la firma PDF."""
    try:
        if not p.exists() or p.stat().st_size <= 5000:
            return False
        with p.open("rb") as f:
            return _is_pdf(f.read(5))
    except Exception:
        return False


async def _esperar_turnstile(page, timeout_seg: int = 90) -> bool:
    """Espera el token de Cloudflare Turnstile (chulo verde)."""
    sel = "input[name='cf-turnstile-response']"
    print("  Esperando validación Cloudflare...", end="", flush=True)
    for i in range(timeout_seg):
        token = await page.evaluate(
            "() => { const el = document.querySelector(\"input[name='cf-turnstile-response']\"); return el ? el.value : null; }"
        )
        if token:
            print(f" OK ({i+1}s)")
            return True
        if i == 5:
            existe = await page.locator(sel).count()
            if existe == 0 and not await page.locator(
                "iframe[src*='challenges.cloudflare.com'], iframe[src*='turnstile']"
            ).count():
                print(" (sin captcha)")
                return True
        await asyncio.sleep(1)
    print(" TIMEOUT")
    return False


async def _safe_content(page) -> str:
    for _ in range(5):
        try:
            return (await page.content()).lower()
        except Exception:
            await asyncio.sleep(0.5)
    return ""


async def descargar_factura(page, cufe: str, carpeta: Path) -> dict:
    """Descarga el PDF de un CUFE a `carpeta/factura_<cufe[:20]>.pdf`."""
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"factura_{cufe[:20]}.pdf"

    if es_pdf_valido(destino):
        print("  -> ya existe, skip")
        return {"cufe": cufe, "ok": True, "archivo": str(destino), "skip": True}

    url = DIAN_URL.format(cufe=cufe)
    print(f"  -> {cufe[:20]}...", end="", flush=True)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    except PWTimeoutError:
        print(" TIMEOUT goto")
        return {"cufe": cufe, "ok": False, "error": "timeout en goto"}

    try:
        input_cufe = page.locator("input[type='text'], input[type='search']").first
        if await input_cufe.count() > 0:
            await input_cufe.fill("")
            await input_cufe.fill(cufe)
    except Exception:
        pass

    await asyncio.sleep(2)

    for intento in range(4):
        try:
            await page.locator(
                "button:has-text('Buscar'), input[type='submit'][value*='Buscar']"
            ).first.click(timeout=10_000)
        except PWTimeoutError:
            return {"cufe": cufe, "ok": False, "error": "botón Buscar no encontrado"}

        await asyncio.sleep(2)
        contenido = await _safe_content(page)

        if "falta token" in contenido:
            espera = 5 + intento * 5
            print(f" falta token #{intento+1}, espero {espera}s...", end="", flush=True)
            await asyncio.sleep(espera)
            continue

        pdf_selectors = [
            "a:has-text('Descargar PDF')",
            "button:has-text('Descargar PDF')",
            "a[href*='DownloadPDF']",
        ]
        pdf_locator = None
        for _ in range(45):
            for sel in pdf_selectors:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    pdf_locator = loc
                    break
            if pdf_locator is not None:
                break
            await asyncio.sleep(1)
        if pdf_locator is None:
            continue

        await _esperar_turnstile(page, timeout_seg=30)

        pdf_responses: list = []

        def _on_response(resp):
            try:
                ctype = (resp.headers.get("content-type") or "").lower()
            except Exception:
                ctype = ""
            url_r = resp.url
            if "pdf" in ctype or url_r.lower().endswith(".pdf") or "downloadpdf" in url_r.lower():
                pdf_responses.append(resp)

        page.context.on("response", _on_response)
        pages_antes = set(page.context.pages)
        download_obj = None
        try:
            for click_attempt in range(3):
                try:
                    async with page.expect_download(timeout=3_000) as dl_info:
                        await pdf_locator.click(timeout=15_000)
                    download_obj = await dl_info.value
                    break
                except PWTimeoutError:
                    pass
                for _ in range(20):
                    if pdf_responses or download_obj:
                        break
                    await asyncio.sleep(0.5)
                if pdf_responses or download_obj:
                    if pdf_responses:
                        await asyncio.sleep(0.5)
                    break
                if click_attempt < 2:
                    await _esperar_turnstile(page, timeout_seg=15)
                    await asyncio.sleep(2)

            if download_obj is not None:
                await download_obj.save_as(destino)
                print(" OK")
                return {"cufe": cufe, "ok": True, "archivo": str(destino)}

            # Leer/recuperar el body de la response PDF capturada en network.
            for resp in pdf_responses:
                try:
                    body = await resp.body()
                    if body and len(body) > 5000 and _is_pdf(body):
                        destino.write_bytes(body)
                        print(" OK (network)")
                        return {"cufe": cufe, "ok": True, "archivo": str(destino)}
                except Exception:
                    pass
                try:
                    req = resp.request
                    method = (req.method or "GET").upper()
                    if method == "POST":
                        r = await page.context.request.post(resp.url, data=req.post_data or "")
                    else:
                        r = await page.context.request.get(resp.url)
                    r_body = await r.body()
                    if r.ok and len(r_body) > 5000 and _is_pdf(r_body):
                        destino.write_bytes(r_body)
                        print(" OK (refetch)")
                        return {"cufe": cufe, "ok": True, "archivo": str(destino)}
                except Exception:
                    pass

            # Si el click abrió pestaña nueva, bajar de su URL.
            for p in page.context.pages:
                if p in pages_antes or p.is_closed():
                    continue
                try:
                    await p.wait_for_load_state("domcontentloaded", timeout=10_000)
                    r = await page.context.request.get(p.url)
                    if r.ok:
                        pop_body = await r.body()
                        if _is_pdf(pop_body):
                            destino.write_bytes(pop_body)
                            await p.close()
                            print(" OK (popup)")
                            return {"cufe": cufe, "ok": True, "archivo": str(destino)}
                except Exception:
                    pass
                try:
                    await p.close()
                except Exception:
                    pass

            snap = carpeta / f"debug_{cufe[:10]}.png"
            try:
                await page.screenshot(path=str(snap), full_page=True)
            except Exception:
                pass
            print(f" sin descarga (ver {snap.name})")
            return {"cufe": cufe, "ok": False, "error": f"PDF no descargado (ver {snap.name})"}
        except Exception as e:
            print(f" error: {str(e)[:60]}")
            return {"cufe": cufe, "ok": False, "error": str(e)[:200]}
        finally:
            try:
                page.context.remove_listener("response", _on_response)
            except Exception:
                pass

    print(" captcha falló tras 4 intentos")
    return {"cufe": cufe, "ok": False, "error": "captcha no validó tras 4 intentos"}


async def descargar_facturas(
    terceros: list[dict],
    carpeta_facturas: Path,
    cdp_url: str = "http://localhost:9222",
    headless: bool = False,
) -> list[dict]:
    """
    Descarga el PDF de cada tercero. `terceros` = lista de dicts con
    claves: nit, nombre, cufe. Devuelve la lista de resultados.
    """
    carpeta_facturas.mkdir(parents=True, exist_ok=True)
    resultados: list[dict] = []

    async with async_playwright() as pw:
        if cdp_url:
            print(f"Conectando a Chrome via CDP en {cdp_url}...")
            browser = await pw.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context(
                accept_downloads=True
            )
            page = context.pages[0] if context.pages else await context.new_page()
        else:
            perfil = carpeta_facturas.parent / ".chrome_profile"
            perfil.mkdir(parents=True, exist_ok=True)
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=str(perfil), channel="chrome",
                headless=headless, accept_downloads=True,
            )
            page = context.pages[0] if context.pages else await context.new_page()

        total = len(terceros)
        for i, t in enumerate(terceros, start=1):
            nit = str(t.get("nit", "")).strip()
            nombre = str(t.get("nombre", "")).strip()
            cufe = str(t.get("cufe", "")).strip()
            print(f"\n[{i}/{total}] {nombre or nit}")
            if not cufe:
                resultados.append({"nit": nit, "nombre": nombre, "ok": False, "error": "sin CUFE"})
                continue
            try:
                res = await descargar_factura(page, cufe, carpeta_facturas / carpeta_segura(nit or nombre))
            except Exception as e:
                res = {"cufe": cufe, "ok": False, "error": f"excepcion: {str(e)[:200]}"}
            res.update({"nit": nit, "nombre": nombre})
            resultados.append(res)

        if not cdp_url:
            await context.close()

    return resultados
