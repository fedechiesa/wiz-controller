# Validación de WiZ Controller 2.1

Fecha: 22 de octubre de 2026. Entorno: Windows 10 x64 (19045), Python 3.13.3, CustomTkinter 5.2.2, pywizlight 0.6.6, pystray 0.19.5, Pillow 13.0.0 y PyInstaller 6.22.3.

## Resultado automatizado

| Verificación | Resultado |
| --- | --- |
| Lógica, configuración, migración, adaptadores y runtime con mocks | 51 aprobados |
| Widgets Tk reales con red simulada | 21 aprobados |
| API nativa de Windows | 5 aprobados |
| Total con `WIZ_GUI_TESTS=1` y `WIZ_NATIVE_TESTS=1` | **77 aprobados, sin omisiones** |
| `compileall` | Sin errores |
| `pip check` | Sin incompatibilidades |
| `git diff --check` | Sin errores de espacios en los cambios |
| Build de PyInstaller | Correcto; `dist/WiZController/WiZController.exe` |
| Formato PE del ejecutable | Subsistema gráfico Windows, sin consola |
| Prueba de escritorio desde Python | Bandeja lista, 4/4 atajos registrados, cierre limpio |
| Prueba del ejecutable en Windows | Salida 0, `frozen: true`, bandeja lista, 4/4 atajos registrados, cierre limpio |
| Paquete y bytecode propios | Sin configuración personal, logs, tests ni IP reales de las bombillas |
| `lighting.py` | Idéntico byte a byte a la versión 2.0 publicada |

Las excepciones de timeout, conflictos y fallas de bandeja que aparecen en el log de tests son intencionales. Se prueban las rutas de recuperación, no indican errores de la suite.

El ejecutable generado tiene SHA-256:

```text
F77D9DEE2DEAF3C448C0309CF4EF59A576EDA8A4D030052FCA9C0A69E5BE0FF6
```

La publicación del código de 2.1 excluye los binarios y los resultados locales de compilación y diagnóstico, que quedan en carpetas ignoradas por Git.

## Archivos modificados y creados

| Grupo | Archivos |
| --- | --- |
| Entrada y configuración modificadas | `main.py`, `config.example.json`, `requirements.txt`, `wiz_controller/models.py`, `wiz_controller/storage.py`, `wiz_controller/integrations.py` |
| Interfaz modificada | `wiz_controller/ui.py`, `docs/dashboard.png` |
| Integraciones nuevas | `wiz_controller/desktop.py`, `desktop_actions.py`, `hotkeys.py`, `instance.py`, `paths.py`, `tray.py` (todos dentro de `wiz_controller/`) |
| Empaquetado nuevo | `WiZController.spec`, `requirements-build.txt`, `scripts/build.ps1`, `scripts/generate_icon.py`, `assets/wiz-controller.ico`, `assets/wiz-controller.png` |
| Tests modificados | `tests/test_runtime.py`, `tests/test_ui.py` |
| Tests nuevos | `tests/test_desktop.py`, `tests/test_paths_migration.py`, `tests/test_windows_native.py` |
| Documentación y reglas modificadas | `README.md`, `docs/VALIDATION.md`, `.gitignore`, `.gitattributes` |
| Guías nuevas | `docs/BUILD.md`, `docs/DAILY_USE.md` |

Dependencias de ejecución agregadas: pystray y Pillow. PyInstaller y sus auxiliares/versiones fijadas se declaran por separado en `requirements-build.txt`.

## Qué se probó

- Todos los casos previos de encendido, apagado, brillo, RGB/blanco, temperatura, confirmación, timeout y captura de escenas.
- Acciones del menú de bandeja y teclado en la cola de Tk, sin acceso a widgets desde trabajadores.
- Supresión de acciones repetidas y de escenas idénticas en curso. Cancelación de un alternado pendiente al elegir una orden explícita.
- Alternado basado en lectura de las dos bombillas, sin asumir el estado de una desconectada.
- Creación y cierre real de un ícono de bandeja Windows; fallo deliberado de creación de ventana y liberación del hilo de setup de pystray.
- Registro nativo de cuatro combinaciones, conflicto al intentar registrarlas de nuevo, entrega de acciones mediante `WM_HOTKEY` y registro exitoso después de liberarlas.
- Mutex y evento de instancia única: detección de una segunda instancia, señal de restauración y liberación de handles. También se lanzó otro proceso Python para verificar el caso entre procesos.
- Cierre de Tk frente a bandeja lista/no disponible y salida completa independiente de la preferencia de la X.
- Cierre de asyncio con cancelación de tareas activas y pendientes; ejecución de su limpieza y terminación del hilo.
- Persistencia de preferencias, rechazo de combinaciones repetidas/F12 y compatibilidad con JSON de 2.0 sin los nuevos campos.
- Directorios en modo Python y congelado, rutas de recursos, comando de inicio de Windows en ambos modos y quoting de rutas con espacios. Las modificaciones de registro se prueban con mocks.
- Migración de configuración y escenas válidas sin borrar originales ni sobreescribir destinos; fuentes inválidas, fuentes ausentes y separación entre recursos y datos persistentes.
- UI al cambiar IP, conservar referencias de escenas, cambiar escala y apilar tarjetas en una ventana estrecha.
- Arranque real del `.exe` con `--smoke-test --desktop-check --data-dir` en una carpeta aislada. Se verificaron recursos empaquetados, bandeja, atajos registrados y cierre del supervisor sin comunicación con bombillas.
- Captura actualizada del dashboard con IP ficticias y revisión visual del ícono propio.

## Datos y privacidad

La revisión para publicación no modifica los archivos personales de `data/` ni de `%LOCALAPPDATA%/WiZController`. Al primer inicio normal de 2.1, se importan los archivos válidos que falten del directorio anterior al persistente; los originales permanecen intactos. La migración se comprobó con fixtures aisladas en los tests; no se atribuye al usuario una prueba manual específica de migración.

Los ejemplos usan direcciones ficticias. Se revisaron los archivos públicos mediante búsquedas de patrones de credenciales, tokens, claves privadas, IP privadas y rutas del workspace; no se detectaron esos datos. El `.spec` usa recursos explícitos. Se inspeccionaron el contenido del paquete y las constantes del bytecode propio para comprobar que no incorporen las direcciones personales existentes.

`.gitignore` excluye entorno virtual, cachés, `data/`, logs, archivos de credenciales, `build/`, `dist/`, ejecutables y ZIP. Solo el código, los tests, los ejemplos anónimos, los recursos de la aplicación y la documentación se incluyen en la publicación del código.

## Validación física y manual

El usuario confirmó las siguientes pruebas manuales satisfactorias de **WiZ Controller 2.1 en Windows**:

- Las dos bombillas WiZ conectan y responden.
- Encendido, apagado, brillo, colores y escenas funcionan.
- El ejecutable de Windows abre correctamente.
- Los atajos globales fueron probados y funcionan.
- La interfaz y el control de iluminación están estables.

El protocolo de iluminación y las escenas incorporadas se conservaron. Esta confirmación corresponde al setup del usuario; no certifica otros modelos, firmwares o equipos. No se especificó la edición o versión de Windows de la validación manual.

## Comprobaciones adicionales no confirmadas manualmente

1. Recepción de atajos dentro de cada juego, en pantalla completa exclusiva, con anticheat o distintos permisos. Los tests nativos verifican el registro y `WM_HOTKEY`; la confirmación manual de atajos no especifica esos escenarios.
2. Inicio real después de cerrar sesión/reiniciar Windows, tanto con Python como con el paquete, y desactivación posterior desde Settings.
3. Comportamiento de la bandeja con Explorer reiniciado, íconos ocultos, suspensión/reanudación y desconexiones reales de la red. La bandeja tiene pruebas automatizadas nativas, pero no se informó una validación manual específica de estos casos.
4. Migración manual de datos, recuperación de configuraciones inválidas y paquete completo en otro equipo Windows sin Python.
5. Compatibilidad general con Windows 11: las pruebas de desarrollo se hicieron en Windows 10 x64 y la confirmación manual del usuario no especifica versión.

La vista previa sigue siendo aproximada; una confirmación acredita la respuesta del dispositivo y no una medición de luz. No hay OBS ni eventos de streaming en esta versión. Bandeja y atajos funcionan de forma independiente de esa futura fase.
