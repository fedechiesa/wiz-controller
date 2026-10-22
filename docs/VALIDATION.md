# Validación de WiZ Controller 2.0

Fecha: 22 de octubre de 2026. Entorno: Windows, Python 3.13.3, CustomTkinter 5.2.2 y pywizlight 0.6.6.

## Resultado automatizado

| Verificación | Resultado |
| --- | --- |
| Tests de modelos, JSON, iluminación, runtime e inicio automático con mocks | 31 aprobados |
| Tests de widgets Tk reales con worker de red simulado | 14 aprobados |
| Total con `WIZ_GUI_TESTS=1` | 45 aprobados |
| `main.py --smoke-test` | Ventana creada y cerrada sin enviar órdenes; salida 0 |
| `compileall` sobre main, módulos y tests | Sin errores de sintaxis/importación durante las pruebas |
| `pip check` | Sin incompatibilidades instaladas |
| Archivos JSON de ejemplo | Deserializados y validados por los modelos |
| Revisión visual del dashboard | Captura real de la ventana, sin estados físicos simulados |

Los mensajes de advertencia que aparecen en los tests de JSON corrupto, timeout y confirmación fallida son intencionales: esos tests verifican precisamente el manejo de errores.

## Revisión para publicación

- Repositorio Git propio inicializado en la carpeta del proyecto, rama `main`, sin commits ni remoto configurado. El índice queda vacío para revisión antes del primer commit.
- Se revisaron los 23 archivos propuestos para versionar. No se detectaron credenciales, claves privadas, tokens de servicios, rutas de usuario ni IP privadas en esos archivos mediante búsqueda de patrones y revisión del contenido.
- Las direcciones reales se conservaron en `data/config.json`, excluido de Git. Código, ejemplos, tests y captura usan direcciones ficticias del bloque de documentación `192.0.2.0/24`.
- Se regeneró y revisó visualmente `docs/dashboard.png`; no tiene metadatos de texto o EXIF.
- Se comprobó `git check-ignore` para entorno virtual, cachés, configuración personal, logs rotados, variables de entorno, claves, temporales de tests y artefactos de compilación. Los ejemplos JSON y la captura permanecen publicables.
- Se verificó mediante SHA-256 que `main.py`, iluminación, runtime, interfaz, persistencia e integraciones no cambiaron durante esta preparación. En `models.py` solo se anonimizaron los valores iniciales de IP y se añadió un comentario; los tests se ajustaron a direcciones ficticias.
- Se volvieron a ejecutar los 45 tests, la apertura sin red, `compileall` y `pip check`. No se enviaron órdenes a las bombillas durante esta revisión.

La búsqueda de patrones complementa la revisión; antes de agregar archivos nuevos conviene revisar también su contenido y cualquier imagen, porque `.gitignore` no inspecciona datos dentro de archivos públicos.

## Cobertura relevante

- Los valores públicos y los tests usan IP ficticias; las IP reales se guardan en `data/config.json`, excluido de Git, y se editan desde Settings.
- Validación de IP duplicadas/incorrectas, brillo, RGB, temperatura y escenas incompletas.
- Creación, edición, renombrado y eliminación de escenas; referencia de escena de inicio actualizada desde la UI.
- Persistencia local, protección de JSON inválido y conservación del archivo anterior ante un fallo de reemplazo.
- Payloads construidos con el `PilotBuilder` real: encendido sin alterar ajustes, apagado, brillo, RGB/blanco y temperatura.
- Verificación de la transformación RGB a canales nativos, preservación de esos canales al capturar escenas y rechazo de respuestas incompatibles o incompletas.
- Timeout, cancelación y cierre del transporte; segunda lectura ante una transición de firmware.
- Serialización de operaciones para una misma IP y concurrencia entre las dos IP.
- Cola de resultados con errores diferenciados de éxito, consumida desde Tk.
- Debounce: 80 movimientos de un slider producen una sola orden con el último valor.
- Una selección pendiente por canal; conservación del color al cambiar brillo o pulsar Encender.
- Escenas que cancelan sliders pendientes y mantienen colores independientes por canal.
- Errores sin falso encendido confirmado, recuperación al reconectar y descarte de respuestas de una IP anterior.
- Guardado de Settings, validación antes de reemplazar configuración y renderizado de todas las pantallas.
- Cambio de escala después de navegar, limpieza de callbacks de menús y tarjetas apiladas en una ventana estrecha al 125%.
- Registro de inicio automático probado exclusivamente con `winreg` simulado. No se habilitó el inicio automático real durante las pruebas.

## Validación física informada

El usuario confirmó pruebas físicas satisfactorias con las dos bombillas WiZ: encendido, apagado, colores, brillo y escenas. Esta confirmación corresponde a su setup; no implica certificación para todos los modelos o firmwares.

En la revisión para publicación no se enviaron nuevas órdenes a dispositivos: se ejecutaron tests con mocks y pruebas de apertura sin red. El inicio real de Windows y las futuras integraciones siguen requiriendo validación adicional.

## Comprobaciones de regresión y otros equipos

La siguiente lista sirve para repetir la validación al cambiar de equipo, bombillas, firmware o funciones. No representa una falla conocida del setup ya probado.

1. Ejecutar `main.py` normalmente con la PC y las bombillas en la misma red. Verificar que la primera consulta muestre las dos disponibles y que no se cambie su iluminación al iniciar sin escena seleccionada.
2. Probar encendido, apagado, brillo mínimo/máximo, colores rápidos y selector RGB en cada canal; comprobar que el otro canal no cambie.
3. Probar encendido, apagado, brillo y color globales. Comparar la vista previa aproximada con las luces y revisar cualquier mensaje de ajuste no confirmado.
4. Aplicar las cinco escenas; validar especialmente soporte de 2700 K/4000 K y la tolerancia de los canales RGB/blanco del firmware. Los blancos requieren una bombilla con temperatura ajustable.
5. Crear una escena con colores y brillo diferentes, incluyendo un canal apagado. Guardar, editar, aplicar y eliminar. Reiniciar y verificar que persistan las escenas y nombres guardados.
6. Cambiar una luz desde la aplicación WiZ del celular y esperar una consulta automática (cada 12 segundos cuando está libre) o pulsar Reconectar.
7. Desconectar una bombilla, enviar una orden y comprobar que la interfaz siga respondiendo y reporte el error. Reconectarla y verificar recuperación automática o mediante Reconectar.
8. Mover sliders rápidamente, aplicar una escena durante una orden pendiente y cerrar durante un timeout. Comprobar la respuesta real del firmware y revisar `data/controller.log` si aparece un error.
9. Cambiar una IP desde Settings, guardar y verificar la conexión con la nueva dirección. Configurar una escena de inicio y comprobar su aplicación al abrir de nuevo.
10. Activar inicio con Windows desde Settings, cerrar sesión y entrar de nuevo. Desactivarlo y verificar que la entrada se retire. Esta comprobación modifica únicamente la entrada propia de inicio automático.
11. Revisar selector de color nativo, escala de Windows/DPI, maximizado y desplazamiento en el monitor del setup. La captura de referencia está en `docs/dashboard.png`.

## Límites y siguiente fase

- Vista previa aproximada, sin calibración de pantalla ni sensor de color. Una confirmación acredita la respuesta del dispositivo; no mide físicamente la luz.
- Las escenas aplican ajustes estáticos a dos canales, no efectos animados. Dos operaciones en paralelo no garantizan simultaneidad exacta a nivel de hardware.
- Cada fase de red tiene timeout de 7 segundos; envío y lecturas de verificación pueden acumular más tiempo. La UI no espera esas operaciones en el hilo principal.
- Las capturas guardan el último estado leído, no una suscripción en tiempo real. Efectos dinámicos activados desde otra app no se reproducen como animación al capturarlos.
- OBS, atajos globales, bandeja y eventos del stream están pendientes. Se dejó una interfaz de adaptadores y una cola segura para solicitar escenas, sin instalar componentes ni alterar OBS.
- Próxima fase: bandeja/atajos y finalmente obs-websocket optativo, con pruebas de regresión en hardware y otros firmwares.
