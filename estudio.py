#!/usr/bin/env python3
"""Asistente de estudio: pulsa la tecla Copilot, captura la pantalla y Claude
te explica lo que estás leyendo. Luego puedes hacerle preguntas de seguimiento.

Usa Claude Code en segundo plano (`claude -p`), así que funciona con tu plan
Pro sin API key ni costo extra.

Uso:
    estudio.py              abre la ventana
    estudio.py --capturar   (lo usa el atajo de Copilot) captura y lo manda a
                            la ventana; si no está abierta, la abre
"""
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QImage
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLineEdit, QTextBrowser, QVBoxLayout, QWidget,
)

NOMBRE_SOCKET = "claude-estudio"
CARPETA = Path.home() / ".cache" / "claude-estudio"  # carpeta de trabajo de Claude Code
CAPTURA = CARPETA / "captura.png"
MODELO = "sonnet"  # rápido y gasta menos de tu límite Pro; "opus" para más calidad
LADO_MAX = 2000  # px, lado largo de la captura que se envía

SYSTEM = (
    "Responde siempre en español, con tono neutro y directamente a lo que "
    "pregunta el usuario o aparece en la imagen. Usa un máximo total de 20 "
    "palabras por respuesta, también si hay varias preguntas. No añadas "
    "introducciones, opiniones, relleno ni explicaciones innecesarias. No "
    "describas elementos irrelevantes de la pantalla ni menciones archivos."
)

ESTILO = """
QWidget { background: transparent; color: #d4d4d4; font-size: 12px; }
QTextBrowser { background: transparent; border: none; padding: 10px; }
QLineEdit { background: transparent; border: none;
padding: 7px; color: #e5e5e5; }
"""


# ---------------------------------------------------------------- captura

def capturar_pantalla() -> QImage | None:
    """Captura toda la pantalla sin flash en GNOME; usa el portal como alternativa."""
    from gi.repository import Gio, GLib

    bus = Gio.bus_get_sync(Gio.BusType.SESSION)

    # GNOME's screenshot portal always requests a flash. Use Shell's screenshot
    # API with flash disabled when it is available, then fall back to the portal.
    CARPETA.mkdir(parents=True, exist_ok=True)
    try:
        respuesta = bus.call_sync(
            "org.gnome.Shell.Screenshot", "/org/gnome/Shell/Screenshot",
            "org.gnome.Shell.Screenshot", "Screenshot",
            GLib.Variant("(bbs)", (False, False, str(CAPTURA))),
            GLib.VariantType("(bs)"), Gio.DBusCallFlags.NONE, -1, None)
        exito, ruta = respuesta.unpack()
        if exito:
            imagen = QImage(ruta)
            if not imagen.isNull():
                return imagen
    except GLib.Error:
        pass

    sender = bus.get_unique_name()[1:].replace(".", "_")
    token = f"estudio{random.randint(0, 10**9)}"
    handle = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
    loop = GLib.MainLoop()
    resultado = {}

    def al_responder(_c, _s, _p, _i, _sig, params):
        codigo, datos = params.unpack()
        resultado["uri"] = datos.get("uri") if codigo == 0 else None
        loop.quit()

    sub = bus.signal_subscribe(
        "org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request",
        "Response", handle, None, Gio.DBusSignalFlags.NO_MATCH_RULE, al_responder)
    bus.call_sync(
        "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.Screenshot", "Screenshot",
        GLib.Variant("(sa{sv})", ("", {
            "handle_token": GLib.Variant("s", token),
            "interactive": GLib.Variant("b", False),
        })),
        GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, -1, None)
    GLib.timeout_add_seconds(20, loop.quit)
    loop.run()
    bus.signal_unsubscribe(sub)

    uri = resultado.get("uri")
    if not uri:
        return None
    ruta = Path(unquote(urlparse(uri).path))
    imagen = QImage(str(ruta))
    ruta.unlink(missing_ok=True)  # el portal la guarda en Imágenes; no la dejamos ahí
    return None if imagen.isNull() else imagen


def guardar_captura(imagen: QImage):
    CARPETA.mkdir(parents=True, exist_ok=True)
    if max(imagen.width(), imagen.height()) > LADO_MAX:
        imagen = imagen.scaled(LADO_MAX, LADO_MAX, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
    imagen.save(str(CAPTURA), "PNG")


def ruta_claude() -> str | None:
    # el atajo de GNOME no siempre tiene ~/.local/bin en el PATH
    return shutil.which("claude") or next(
        (str(p) for p in [Path.home() / ".local/bin/claude"] if p.exists()), None)


# ---------------------------------------------------------------- Claude

class HiloClaude(QThread):
    fragmento = pyqtSignal(str)
    reiniciar = pyqtSignal()  # el texto previo era un preámbulo antes de leer la imagen
    terminado = pyqtSignal(str, str)  # texto final, id de sesión
    error = pyqtSignal(str)

    def __init__(self, prompt: str, sesion: str | None):
        super().__init__()
        self.prompt = prompt
        self.sesion = sesion

    def run(self):
        claude = ruta_claude()
        if not claude:
            self.error.emit("No encuentro el comando «claude». ¿Está instalado Claude Code?")
            return
        cmd = [claude, "-p", self.prompt, "--output-format", "stream-json", "--verbose",
               "--include-partial-messages", "--tools", "Read", "--strict-mcp-config",
               "--model", MODELO, "--append-system-prompt", SYSTEM]
        if self.sesion:
            cmd += ["--resume", self.sesion]
        try:
            proc = subprocess.Popen(cmd, cwd=CARPETA, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
        except OSError as e:
            self.error.emit(f"No se pudo ejecutar Claude Code: {e}")
            return
        resultado = None
        for linea in proc.stdout:
            try:
                ev = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "stream_event":
                e = ev["event"]
                if e.get("type") == "content_block_start" and e["content_block"]["type"] == "tool_use":
                    self.reiniciar.emit()
                elif e.get("type") == "content_block_delta" and e["delta"].get("type") == "text_delta":
                    self.fragmento.emit(e["delta"]["text"])
            elif ev.get("type") == "result":
                resultado = ev
        proc.wait()
        if not resultado or resultado.get("is_error"):
            detalle = (resultado or {}).get("result") or proc.stderr.read().strip()[-400:]
            self.error.emit(f"Claude Code falló: {detalle or 'sin detalles'}")
            return
        self.terminado.emit(resultado.get("result", ""), resultado.get("session_id", ""))


# ---------------------------------------------------------------- ventana
class Ventana(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Asistente de estudio · Claude")
        self.resize(480, 140)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)  # Sin bordes
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # Fondo transparente
        self.sesion = None
        self.historial_md = ""
        self.respuesta_md = ""
        self.hilo = None
        self.mostrar_al_terminar = False
        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(True)
        self.chat.setFixedHeight(72)
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("Pregunta algo sobre lo que estás leyendo…")
        self.entrada.returnPressed.connect(self.preguntar)
        fila = QHBoxLayout()
        fila.addWidget(self.entrada)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)
        lay.addWidget(self.chat, 1)
        lay.addLayout(fila)
        self.servidor = QLocalServer(self)
        QLocalServer.removeServer(NOMBRE_SOCKET)
        self.servidor.listen(NOMBRE_SOCKET)
        self.servidor.newConnection.connect(self.al_conectar)
        # --- señal desde el atajo de teclado
    def al_conectar(self):
        con = self.servidor.nextPendingConnection()
        con.waitForReadyRead(1000)
        if bytes(con.readAll()).strip() == b"capturar":
            self.capturar(mostrar_despues=True)
        con.disconnectFromServer()
    def ocupado(self, si: bool):
        self.entrada.setDisabled(si)
    # --- captura: empieza un tema nuevo
    def capturar(self, pregunta: str | None = None, mostrar_despues: bool = False):
        if self.hilo and self.hilo.isRunning():
            return
        QApplication.processEvents()
        imagen = capturar_pantalla()
        if mostrar_despues:
            self.mostrar_al_terminar = True
            self.traer_al_frente()
            QTimer.singleShot(100, self.traer_al_frente)
        if imagen is None:
            self.mostrar_al_terminar = False
            return
        guardar_captura(imagen)
        self.sesion = None
        self.historial_md = ""
        if pregunta:
            self.entrada.clear()
            self.historial_md = f"**Tú:** {pregunta}\n\n"
        # self.raise_()
        # self.activateWindow()
        prompt = (f"Lee la imagen {CAPTURA.name} (captura de mi pantalla) y "
                  "responde brevemente a lo que pregunta.")
        if pregunta:
            prompt = (f"Lee la imagen {CAPTURA.name} (captura de mi pantalla) "
                      f"y responde brevemente a esta pregunta: {pregunta}")
        self.enviar(prompt)
    # --- pregunta de seguimiento
    def preguntar(self):
        texto = self.entrada.text().strip()
        if not texto or (self.hilo and self.hilo.isRunning()):
            return
        if not self.sesion:
            self.capturar(texto)
            return
        self.entrada.clear()
        self.historial_md += f"\n\n---\n\n**Tú:** {texto}\n\n"
        self.enviar(texto)
    def enviar(self, prompt: str):
        self.respuesta_md = ""
        self.ocupado(True)
        self.pintar()
        self.hilo = HiloClaude(prompt, self.sesion)
        self.hilo.fragmento.connect(self.al_fragmento)
        self.hilo.reiniciar.connect(self.al_reiniciar)
        self.hilo.terminado.connect(self.al_terminar)
        self.hilo.error.connect(self.al_error)
        self.hilo.start()
    def al_fragmento(self, texto):
        self.respuesta_md += texto
        self.pintar()
    def al_reiniciar(self):
        self.respuesta_md = ""
        self.pintar()
    def al_terminar(self, texto, sesion):
        self.sesion = sesion or self.sesion
        self.historial_md += texto or self.respuesta_md
        self.respuesta_md = ""
        self.ocupado(False)
        self.entrada.setFocus()
        if self.mostrar_al_terminar:
            self.mostrar_al_terminar = False
            QTimer.singleShot(0, self.traer_al_frente)
    def al_error(self, msg):
        self.respuesta_md = ""
        self.ocupado(False)
        self.pintar()
        if self.mostrar_al_terminar:
            self.mostrar_al_terminar = False
            QTimer.singleShot(0, self.traer_al_frente)
    def traer_al_frente(self):
        self.setWindowState(Qt.WindowState.WindowNoState)
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        if self.windowHandle():
            self.windowHandle().requestActivate()
    def pintar(self):
        self.chat.setMarkdown(self.historial_md + self.respuesta_md)
        barra = self.chat.verticalScrollBar()
        barra.setValue(barra.maximum())
def avisar_ventana_abierta() -> bool:
    """Si la ventana ya está abierta, le pide que capture. Devuelve True si lo logró."""
    sock = QLocalSocket()
    sock.connectToServer(NOMBRE_SOCKET)
    if not sock.waitForConnected(500):
        return False
    sock.write(b"capturar")
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True
def main():
    capturar_al_abrir = "--capturar" in sys.argv
    # XWayland permite respetar la posición inferior solicitada con move().
    if (os.environ.get("XDG_SESSION_TYPE") == "wayland"
            and os.environ.get("DISPLAY")):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    app = QApplication(sys.argv)
    if capturar_al_abrir and avisar_ventana_abierta():
        return
    app.setStyleSheet(ESTILO)
    ventana = Ventana()
    pantalla = app.primaryScreen()
    if pantalla:
        area = pantalla.availableGeometry()
        x = area.x() + (area.width() - ventana.width()) // 2
        y = area.y() + area.height() - ventana.height() - 16
        ventana.move(x, y)
    ventana.show()
    if pantalla:
        QTimer.singleShot(0, lambda: ventana.move(x, y))
    if capturar_al_abrir:
        QTimer.singleShot(300, ventana.capturar)
    sys.exit(app.exec())
if __name__ == "__main__":
    main()
