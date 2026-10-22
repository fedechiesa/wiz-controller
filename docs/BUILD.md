# Build de Windows · WiZ Controller 2.1

## Preparar y compilar

Usá Windows y Python 3.13 de 64 bits. Desde PowerShell en el repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build.ps1
```

`requirements-build.txt` fija las versiones de los paquetes de build y sus dependencias instaladas. No se busca garantizar identidad binaria entre diferentes versiones de Windows/Python o fechas de compilación; el script informa el SHA-256 de cada resultado.

El script ejecuta `pip check` y la suite de tests (los tests de escritorio/nativos requieren sus variables de activación), regenera el ícono propio y ejecuta PyInstaller. `-SkipTests` permite reutilizar una suite ya ejecutada; no omite `pip check`. `-Python RUTA` permite indicar otro entorno. No cambia la política global de PowerShell.

Resultado:

```text
dist/
  WiZController/
    WiZController.exe
    _internal/
      ...dependencias, Tcl/Tk y recursos...
```

Ejecutá `dist\WiZController\WiZController.exe`. La carpeta completa es la unidad de distribución: copiar solo el `.exe` no funciona. Se usa el bootloader gráfico de PyInstaller, sin consola, y un ícono ICO con tamaños 16–256 px. PNG/ICO se generan con `scripts/generate_icon.py` sin descargar imágenes ni usar fuentes externas.

## Recursos y datos persistentes

`WiZController.spec` incluye explícitamente los recursos de CustomTkinter, metadatos de pystray y los dos íconos de `assets/`. PyInstaller recopila los módulos y bibliotecas requeridos. No se hace una copia recursiva del proyecto: no entran `data/`, tests, `.venv/`, `.git/`, credenciales ni configuraciones privadas.

`resource_path` usa el directorio de recursos de PyInstaller para los íconos. `user_data_directory` usa `%LOCALAPPDATA%\WiZController` para configuración, escenas y logs; no escribe datos personales en `_internal`, en el ejecutable ni en Program Files.

La migración automática en desarrollo busca `data/` del proyecto, y empaquetado busca `data/` junto al `.exe`. Para importar desde otra ubicación:

```powershell
.\dist\WiZController\WiZController.exe --migrate-from .\data
```

Solo se copian archivos válidos que falten en el destino; no se sobreescriben archivos persistentes existentes ni se borran originales. No se migran logs. Los ejemplos públicos no son configuraciones personales y no se importan automáticamente.

## Comprobar el resultado sin bombillas

```powershell
$checkDir = Join-Path (Get-Location) 'build\exe-check'
$exe = (Resolve-Path 'dist\WiZController\WiZController.exe').Path
$process = Start-Process -FilePath $exe -ArgumentList @('--smoke-test', '--desktop-check', '--data-dir', ('"' + $checkDir + '"')) -WindowStyle Hidden -Wait -PassThru
$process.ExitCode
Get-Content (Join-Path $checkDir 'smoke-result.json')
```

Se crea la ventana, se inicializa la bandeja real y se cierra sin red ni migración. La salida debe ser 0 y el informe debe indicar `frozen: true`, `tray_ready: true` y `desktop_stopped: true`. Si copiás una configuración ficticia en ese directorio y habilitás sus atajos, el informe compara la cantidad registrada con la esperada. No uses configuraciones personales para compartir estos resultados.

Para probar también la UI y API de Windows desde el código:

```powershell
$env:WIZ_GUI_TESTS = '1'
$env:WIZ_NATIVE_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:WIZ_GUI_TESTS, Env:WIZ_NATIVE_TESTS
```

La prueba nativa registra combinaciones Ctrl+Alt+Shift+F8–F11, comprueba conflictos y liberación, crea un ícono temporal y verifica señalización de otra instancia. La entrega de acciones de teclado se prueba con `WM_HOTKEY`; el comportamiento físico de teclas dentro de juegos debe validarse manualmente.

## Alcance de distribución

El build no modifica OBS, el registro de inicio, el firewall ni publica archivos. Para probar el inicio con Windows usá la opción explícita en Settings y guardá desde la ubicación definitiva del ejecutable.

Los resultados locales `build/`, `dist/`, `.exe` y `.zip` quedan ignorados por Git. La apertura del ejecutable de 2.1 fue validada manualmente en Windows, además de las pruebas automatizadas de escritorio. El paquete no fue firmado ni se adjunta como binario a la publicación del código. La ejecución en otro equipo sin Python y el inicio tras entrar a Windows siguen requiriendo comprobación específica.
