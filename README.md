# WiZ Controller 2.0 · Gaming & Streaming Edition

Centro de iluminación de escritorio para dos bombillas WiZ, con Python 3.13 y CustomTkinter. Control por red local, sin nube, cuentas, bases de datos ni servicios de fondo.

Incluye dashboard con controles globales e individuales, escenas por bombilla, editor de escenas JSON, reconexión automática, preferencias visuales e inicio opcional con Windows. Las operaciones de red se ejecutan fuera del hilo de la interfaz.

![Dashboard de WiZ Controller](docs/dashboard.png)

La captura usa direcciones ficticias y muestra el panel antes de consultar dispositivos. No contiene datos de una red personal.

El funcionamiento fue probado físicamente por el usuario con dos bombillas WiZ: encendido, apagado, colores, brillo y escenas. La suite automatizada usa mocks para poder ejecutarse sin dispositivos físicos.

## Requisitos

- Windows y Python 3.13 con Tcl/Tk (incluido en la instalación estándar de Python para Windows).
- Dos bombillas WiZ compatibles con control local y, para los blancos cálido/neutro, temperatura ajustable.
- PC y bombillas en la misma red, con acceso al puerto UDP 38899 y sus direcciones IPv4 disponibles.
- Acceso a Internet para instalar las dependencias; el control de iluminación funciona por LAN.

## Instalar y ejecutar en Windows

Descargá o cloná el repositorio y abrí PowerShell en la carpeta que contiene `main.py`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Para ejecutar:

```powershell
.\.venv\Scripts\python.exe main.py
```

En la primera ejecución, abrí **Settings**, ingresá las IP de tus bombillas y guardá. Los valores públicos son ficticios y deben reemplazarse; no se descubren automáticamente las IP. No hace falta activar el entorno. Si ya tenés `.venv`, podés reutilizarlo. Para abrir sin consola:

```powershell
.\.venv\Scripts\pythonw.exe main.py
```

Dependencias directas: `pywizlight==0.6.6` y `customtkinter==5.2.2`, declaradas en `requirements.txt`.

La PC y las bombillas deben estar en la misma red y permitir comunicación local WiZ mediante UDP 38899. Si Windows consulta por el firewall, habilitá Python en la red privada correspondiente. Una reserva DHCP en el router ayuda a mantener las IP estables.

## Control diario

- **Dashboard:** encender/apagar ambas luces, brillo y color globales. Cada tarjeta tiene encendido, apagado, brillo, selector RGB, colores rápidos, estado de conexión y vista previa aproximada del último estado leído.
- **Nombres:** editá el título de una tarjeta y presioná Enter o salí del campo. También podés cambiarlos en Settings.
- **Escenas:** Gaming (violeta/cian), Streaming (magenta/azul), Relax (2700 K), Estudio (4000 K) y Noche (azul/violeta tenue).
- **Personalizadas:** creá una combinación distinta por bombilla, guardala, editála o eliminála desde Escenas. Podés indicar encendido, brillo y RGB o blanco por canal. Guardar una escena no la aplica: usá **Aplicar** para enviar los ajustes.
- **Guardar estado leído:** captura la última lectura de ambas luces cuando están disponibles y no hay ajustes pendientes. No inventa colores ni brillo si faltan datos.
- **Reconectar:** consulta las dos bombillas sin reiniciar la aplicación. También se consultan automáticamente cada 12 segundos, si no tienen otra operación en curso.

Cambiar brillo o color enciende la luz, igual que en la versión original. Encender conserva los ajustes que tenga la bombilla. Una escena con un canal apagado envía apagado a ese canal; sus valores guardados de brillo/color no se transmiten mientras está apagado.

## Configuración local

Settings permite editar IP, nombre, escena de inicio, paleta Medianoche/Grafito, acento Violeta/Cian/Magenta y escala 100/110/125%. La escena de inicio está desactivada por defecto para que abrir el panel no cambie las luces.

El código público, los tests y `config.example.json` usan únicamente direcciones de documentación:

| Canal | Nombre | IP ficticia |
| --- | --- | --- |
| bulb1 | Luz 1 | 192.0.2.10 |
| bulb2 | Luz 2 | 192.0.2.11 |

Estas direcciones no corresponden a bombillas reales. Guardá tus IP exclusivamente en `data/config.json`, desde Settings o editando una copia del ejemplo. No publiques ese archivo ni los logs.

Los cambios se guardan en `data/config.json`. Las escenas del usuario se guardan en `data/scenes.json`. La carpeta se resuelve respecto del proyecto, independientemente de la carpeta desde la que ejecutes el programa. Se escribe al guardar desde la interfaz; la ausencia de un archivo usa valores iniciales.

Para configurar manualmente, cerrá el programa y copiá los ejemplos:

```powershell
New-Item -ItemType Directory -Path data -Force
if (-not (Test-Path data/config.json)) {
    Copy-Item config.example.json data/config.json
}
if (-not (Test-Path data/scenes.json)) {
    Copy-Item scenes.example.json data/scenes.json
}
notepad data/config.json
```

Los comandos conservan archivos existentes. Cambiá las IP ficticias por las de tus bombillas antes de ejecutar. El segundo ejemplo agrega una escena llamada Personalizado si aún no existe un archivo de escenas. También podés crearla desde la interfaz.

Los identificadores `bulb1` y `bulb2` permanecen estables al cambiar nombres o IP, para que las escenas sigan apuntando al canal correcto. Se validan IP, nombres, brillo y colores antes de guardar. Las escrituras usan un archivo temporal y reemplazo atómico. Un JSON inválido se conserva: el panel avisa y bloquea su sobrescritura; corregilo o renombralo y volvé a abrir la aplicación.

**Inicio con Windows:** el checkbox de Settings registra únicamente esta aplicación para tu usuario en `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, con el Python del entorno y una ruta absoluta. Solo modifica esa entrada al cambiar la opción y guardar. Desmarcarla y guardar elimina la entrada. Si movés el proyecto o recreás el entorno, volvé a activar la opción. No se modifica OBS ni se requiere administrador.

## Confirmación y errores

Se conserva la comunicación original con `wizlight`, `PilotBuilder`, `turn_on`, `turn_off` y cierre de transporte. Después de una orden se consulta el estado. El panel confirma encendido, brillo y canales de color/temperatura informados; si difieren, muestra **Revisar ajuste**. `pywizlight` transforma RGB en canales RGB y blanco: la verificación usa los valores efectivamente transmitidos. Las capturas guardan esos canales nativos para evitar una segunda conversión.

Cada fase de red tiene un timeout de 7 segundos. Una operación con envío y verificación puede durar más de 7 segundos. Se admite una segunda lectura para transiciones del firmware. La UI sigue disponible durante la espera.

Los sliders esperan 350 ms sin cambios antes de enviar. Hay como máximo una operación activa y una selección pendiente por bombilla; cambios repetidos reemplazan esa selección, conservando color y brillo cuando corresponde. Las dos bombillas operan en paralelo; las órdenes sobre una misma IP se serializan. Aplicar una escena cancela los sliders pendientes para evitar que la sobrescriban.

Tkinter recibe resultados mediante una cola desde un único hilo asyncio. Ningún worker modifica widgets ni llama `after`. Al cambiar IP se cancelan las tareas anteriores y se descartan respuestas antiguas. Si una luz se desconecta se conserva su último estado marcado como tal, sin presentarlo como una lectura actual.

El log local `data/controller.log` rota a los 500 KB con dos copias. Incluye fallos de red y excepciones de interfaz para diagnóstico.

## Estructura

```text
main.py                        Entrada, logging y arranque
wiz_controller/models.py       Configuración y escenas validadas
wiz_controller/storage.py      Persistencia JSON local
wiz_controller/lighting.py     Comandos pywizlight y lectura de confirmación
wiz_controller/runtime.py      Hilo asyncio, serialización por IP y cola de resultados
wiz_controller/ui.py           Dashboard, tarjetas, escenas y Settings
wiz_controller/integrations.py Puerto de integración e inicio automático de Windows
tests/                         Tests de lógica y de widgets con red simulada
config.example.json            Ejemplo de configuración
scenes.example.json            Ejemplo de escena por bombilla
docs/dashboard.png              Captura del dashboard sin datos personales
docs/VALIDATION.md              Resultados automatizados y validación física informada
```

Se mantiene CustomTkinter: permite el diseño oscuro, tarjetas y controles con las dependencias existentes. La previsualización usa dibujo estático de Tk, sin animaciones costosas. La ventana es desplazable para pantallas pequeñas; tamaño mínimo 1050×720. Las tarjetas se apilan al reducir el espacio disponible o aumentar la escala. Se incluye un ajuste de compatibilidad para limpiar callbacks de escala de menús destruidos en CustomTkinter 5.2.2.

## Verificación

Tests de lógica sin dispositivos físicos:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Los tests de escritorio se omiten por defecto. Para ejecutarlos con una sesión gráfica disponible:

```powershell
$env:WIZ_GUI_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:WIZ_GUI_TESTS
```

Arranque de la ventana sin comunicación con bombillas (cierra automáticamente):

```powershell
.\.venv\Scripts\python.exe main.py --smoke-test
.\.venv\Scripts\python.exe -m compileall -q main.py wiz_controller tests
.\.venv\Scripts\python.exe -m pip check
```

Las pruebas usan respuestas y errores simulados únicamente dentro de los tests. El dashboard normal consulta las IP configuradas y no muestra conexiones ficticias.

## Integraciones y siguiente fase

OBS, atajos globales, bandeja y eventos del stream están **pendientes**, claramente identificados en Integraciones. No hay botones que simulen conectarlos. `Integration` define el ciclo `start/stop`; futuros adaptadores pueden enviar nombres a `app.integration_requests`, una cola que Tk procesa y valida. Así no necesitan tocar widgets ni implementar nuevamente la iluminación.

La próxima fase recomendada es agregar bandeja/atajos y después un adaptador optativo de obs-websocket con reconexión y selección explícita de escenas. Las pruebas con otros modelos y firmwares deben acompañar esos cambios. No se instala ni modifica OBS automáticamente.

El inicio real tras entrar a Windows y las futuras integraciones requieren validación adicional. Los resultados y las comprobaciones están en [docs/VALIDATION.md](docs/VALIDATION.md).

## Archivos públicos y privados

Publicá el código, los tests, `requirements.txt`, este README, `.gitignore`, `.gitattributes`, los ejemplos JSON y `docs/`. La carpeta `data/` contiene las IP, preferencias, escenas personales y logs; queda fuera de Git junto con `.venv/`, cachés, archivos temporales y archivos de credenciales conocidos. Los ejemplos no requieren credenciales.

Antes de compartir cambios, revisá `git status --short` y `git diff --cached`. Las reglas de `.gitignore` no ocultan información pegada dentro de código, documentación o capturas, ni eliminan archivos que ya estén versionados.
