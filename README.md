# Asistente de estudio · Claude

Una ventanita para Linux (GNOME). Pulsas la tecla Copilot, captura tu pantalla y
Claude te explica brevemente lo que estás leyendo. Después puedes escribirle
preguntas de seguimiento sobre la misma captura.

Usa [Claude Code](https://claude.com/claude-code) por detrás (`claude -p`), así que
funciona con tu suscripción de Claude (Pro/Max) sin API key ni costo extra.

## Cómo funciona

1. El atajo de teclado ejecuta `asistente-estudio --capturar`.
2. Se hace una captura de pantalla completa. Primero se intenta con la API de
   GNOME Shell (sin flash) y, si no está disponible, con el portal de escritorio.
3. La imagen se guarda en `~/.cache/claude-estudio/captura.png` (reducida a
   2000 px como máximo).
4. Claude Code lee la imagen y la respuesta aparece en la ventana en tiempo real.
5. Lo que escribas en la caja de texto continúa la misma conversación. Cada
   captura nueva empieza una conversación nueva.

Si la ventana ya está abierta, el atajo no abre otra: le pide a la existente
que haga una captura nueva.

## Requisitos

- Linux con GNOME (probado en Wayland; la ventana se abre con XWayland para
  poder colocarla abajo en el centro de la pantalla)
- Python 3.10 o superior
- [Claude Code](https://docs.claude.com/en/docs/claude-code) instalado y con la
  sesión iniciada (`claude` en el terminal debe funcionar)
- PyQt6 y PyGObject

En Ubuntu/Debian, PyGObject es más fácil instalarlo desde el sistema:

```bash
sudo apt install python3-gi gir1.2-glib-2.0
```

## Instalación

```bash
git clone https://github.com/YukiRito2/CheatEX.git
cd CheatEX
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
```

Para probarlo sin compilar:

```bash
.venv/bin/python estudio.py              # abre la ventana
.venv/bin/python estudio.py --capturar   # abre la ventana y captura
```

### Compilar e instalar como ejecutable

```bash
.venv/bin/pip install pyinstaller
./build.sh
```

Esto crea un único ejecutable y lo instala en
`~/.local/bin/asistente-estudio`.

### Asignar la tecla Copilot

En **Configuración → Teclado → Atajos de teclado → Ver y personalizar atajos →
Atajos personalizados**, añade uno nuevo:

- **Nombre:** Asistente de estudio (Claude)
- **Comando:** `/home/TU_USUARIO/.local/bin/asistente-estudio --capturar`
- **Atajo:** pulsa la tecla Copilot. En muchos portátiles GNOME la detecta como
  `Shift+Super+F23` (o `Shift+Super+XF86TouchpadOff`).

Pon la ruta completa en el comando, porque los atajos de GNOME no siempre
tienen `~/.local/bin` en el PATH.

## Uso

- **Tecla Copilot:** captura la pantalla y muestra la explicación.
- **Escribir + Enter:** hace una pregunta de seguimiento sobre la captura.
  Si todavía no hay captura, se hace una con tu pregunta.

## Configuración

Al principio de `estudio.py`:

| Variable   | Para qué sirve                                                          |
|------------|-------------------------------------------------------------------------|
| `MODELO`   | `"sonnet"` (rápido, gasta menos del límite) u `"opus"` (más calidad)     |
| `LADO_MAX` | Tamaño máximo en píxeles del lado largo de la captura que se envía      |
| `SYSTEM`   | Instrucciones de estilo de las respuestas (idioma, longitud, tono)      |
| `ESTILO`   | Hoja de estilos Qt de la ventana                                        |

## Privacidad

Cada captura de pantalla completa se envía a Claude a través de Claude Code.
Antes de pulsar la tecla, cierra o tapa lo que no quieras compartir
(contraseñas, mensajes privados, etc.). La captura local se sobrescribe en cada
uso y se guarda en `~/.cache/claude-estudio/`.

## Solución de problemas

- **«No encuentro el comando claude»:** instala Claude Code y comprueba que
  existe `~/.local/bin/claude` o que `claude` está en el PATH.
- **No pasa nada al pulsar la tecla:** ejecuta el comando del atajo desde un
  terminal para ver los errores y revisa que el atajo apunte a la ruta correcta.
- **La captura falla:** fuera de GNOME se usa el portal
  `xdg-desktop-portal`; asegúrate de tenerlo instalado.
