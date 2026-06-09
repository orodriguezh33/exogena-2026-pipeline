@echo off
REM Abre Chrome real con puerto de depuracion y perfil dedicado para el portal DIAN.
REM portal_runner.py descargar --cdp se conecta a esta instancia.
REM NO cerrar esta ventana mientras corre la descarga.
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="%~dp0.chrome_cdp_profile" ^
  https://catalogo-vpfe.dian.gov.co/User/SearchDocument
