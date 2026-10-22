# Guía de uso diario · WiZ Controller 2.1

La versión 2.1 fue validada manualmente en Windows: conexión y control de ambas bombillas, brillo, colores, escenas, apertura del ejecutable y atajos globales. El usuario confirmó estabilidad de la interfaz y la iluminación. Inicio tras entrar a Windows, escenarios específicos de juegos y recuperación de la bandeja no se consideran confirmados por esa validación.

## Abrir y recuperar la ventana

Ejecutá `main.py` con el Python del entorno o abrí `WiZController.exe`. Si usás una instalación 2.0 anterior, cerrala antes de probar 2.1. Entre instancias de 2.1, abrir de nuevo restaura la ventana existente sin crear otro controlador, volver a aplicar la escena de inicio ni cambiar las luces.

También podés restaurar desde **Abrir WiZ Controller** en el menú del ícono de bandeja. Buscalo en los íconos ocultos de Windows si no está visible junto al reloj.

## Minimizar y salir

- **A la bandeja:** oculta el panel si el ícono está disponible. La iluminación y los atajos habilitados siguen funcionando.
- **X:** con la opción de Settings activa, oculta a la bandeja; si la bandeja está deshabilitada o falló su inicialización, cierra normalmente.
- **Minimizar estándar:** usa la barra de tareas.
- **Salir completamente:** tanto en el panel como en la bandeja, cierra adaptadores, libera los atajos y cancela tareas de red pendientes. No cambia intencionalmente el estado de las luces; una orden ya recibida por una bombilla no puede deshacerse al cerrar.

Para recuperar un panel oculto cuyo ícono no aparece, ejecutá de nuevo el mismo programa: la instancia nueva señaliza a la que ya está abierta. Después podés desactivar la bandeja en Settings y guardar. Si falla la bandeja durante el inicio en segundo plano, el panel se muestra para permitir la recuperación.

## Menú de bandeja

Abrir/restaurar, encender todas, apagar todas, Gaming, Streaming, Relax y salir completamente. Esas acciones entran en la misma cola que usan los atajos y llegan a los controles de iluminación existentes; no crean otro hilo de red ni acceden a Tk desde el menú.

## Configurar atajos

1. Abrí Settings y bajá a **Escritorio y gaming**.
2. Activá **Atajos globales de Windows**.
3. Usá los valores iniciales o escribí combinaciones como `Ctrl+Alt+F9` o `Ctrl+Shift+G`.
4. Guardá y revisá el mensaje de registro. Un atajo ocupado se identifica por acción y combinación; los otros continúan disponibles.

Valores iniciales: Gaming F9, Streaming F10, Relax F11 y Alternar luces F8, todos con Ctrl+Alt. F12 está reservada por Windows; Win y teclas de movimiento sueltas no se aceptan. Al guardar se liberan primero los registros anteriores. Desactivar y guardar los libera también.

**Alternar** lee ambas bombillas antes de decidir. Si alguna está encendida, apaga ambas; si las dos están apagadas, enciende ambas. Con una bombilla desconectada no asume su estado. Mientras hay una operación en curso, otra pulsación de alternado se descarta; una escena u orden explícita cancela un alternado pendiente.

Los atajos registrados consumen solo sus combinaciones. Elegí combinaciones que no uses en tus juegos. Pantalla completa exclusiva, anticheat, otros registros y diferencias de privilegios pueden impedir su recepción; el programa no instala hooks, no registra pulsaciones y no pide administrador para sortear esas restricciones. Se debe probar cada juego y su modo de pantalla.

## Inicio con Windows

En Settings activá **Iniciar WiZ Controller al entrar a Windows** y guardá. Usa una sola entrada `WiZController` en el inicio del usuario actual. En desarrollo apunta al Python del entorno y `main.py`; empaquetado, al ejecutable actual. No apunta a `_internal` ni a archivos extraídos temporales.

El argumento `--background` oculta el panel cuando la bandeja está lista. Si la bandeja está desactivada o falla, queda visible. La escena de inicio, si elegiste una, se aplica solo al iniciar la primera instancia. Por defecto no hay escena de inicio.

Después de mover el proyecto, cambiar el entorno o mover el ejecutable, abrí desde la ubicación nueva y guardá Settings con inicio automático activo para actualizar la ruta. Desmarcar y guardar retira esa única entrada. No se agregó ni modificó una entrada real de inicio automático durante las pruebas de desarrollo.

Al reiniciar Windows se conservan los datos guardados. El inicio tras entrar a Windows requiere comprobación manual en el equipo destino; no se restaura una cola de órdenes que estuviera pendiente antes del reinicio.

## Archivos personales

Abrí `%LOCALAPPDATA%\WiZController` desde el Explorador para encontrar `config.json`, `scenes.json`, `controller.log` y sus dos copias rotadas. El log rota a los 500 KB. Estos archivos pueden contener IP o nombres del setup; no deben publicarse.

Al actualizar desde 2.0, la configuración válida de `data/` se copia solo si no existe su archivo de destino. Los originales no se borran. Desde ese momento, usá Settings o el directorio persistente para editar; el `data/` anterior es una copia histórica. Los JSON inválidos se conservan y se informan para poder corregirlos.

Cambiar brillo o color enciende la luz como en 2.0. El panel diferencia el último estado de uno confirmado y permite Reconectar cuando un dispositivo vuelve a la red. La consulta periódica sigue siendo cada 12 segundos cuando el canal está libre.
