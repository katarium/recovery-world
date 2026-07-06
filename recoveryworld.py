#!/usr/bin/env python3
"""
RecoveryWorld
=============
Un grabador de terminal estilo VHS (https://github.com/charmbracelet/vhs),
escrito en Python puro.

Le das un script ".tape" con comandos tipo:

    Output demo.gif
    Set Shell "bash"
    Set FontSize 18
    Set Width 1200
    Set Height 640
    Set Theme "Dracula"
    Set TypingSpeed 40ms
    Set Framerate 15

    Type "echo Hola RecoveryWorld"
    Enter
    Sleep 1s
    Type "ls -la"
    Enter
    Sleep 2s

...y te devuelve un GIF (o mp4/webm si hay ffmpeg instalado) con la
terminal "actuando" ese script, tipeo incluido.

Uso:
    python3 recoveryworld.py demo.tape

Sólo funciona en Linux/macOS (usa pty). No requiere librerías externas
más que Pillow (pip install pillow).

Limitaciones (a diferencia de VHS real, que usa un navegador headless):
Este es un emulador de terminal ANSI *mínimo* hecho a mano. Soporta lo
más común (colores SGR, movimiento de cursor, scroll, erase), pero no
es un xterm completo — cosas muy elaboradas (mouse, 256 colores exactos,
unicode ancho doble, etc.) pueden no verse perfectas.
"""

import fcntl
import os
import pty
import re
import select
import shlex
import shutil
import struct
import subprocess
import sys
import termios
import threading
import time

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Temas de color (16 colores ANSI: 0-7 normales, 8-15 brillantes)
# ---------------------------------------------------------------------------

THEMES = {
    "Default": {
        "bg": (13, 13, 13), "fg": (230, 230, 230),
        "palette": [
            (0, 0, 0), (205, 49, 49), (13, 188, 121), (229, 229, 16),
            (36, 114, 200), (188, 63, 188), (17, 168, 205), (229, 229, 229),
            (102, 102, 102), (241, 76, 76), (35, 209, 139), (245, 245, 67),
            (59, 142, 234), (214, 112, 214), (41, 184, 219), (255, 255, 255),
        ],
    },
    "Dracula": {
        "bg": (40, 42, 54), "fg": (248, 248, 242),
        "palette": [
            (33, 34, 44), (255, 85, 85), (80, 250, 123), (241, 250, 140),
            (189, 147, 249), (255, 121, 198), (139, 233, 253), (248, 248, 242),
            (98, 114, 164), (255, 110, 110), (105, 255, 148), (255, 255, 165),
            (214, 172, 255), (255, 146, 223), (164, 255, 255), (255, 255, 255),
        ],
    },
    "Monokai": {
        "bg": (39, 40, 34), "fg": (248, 248, 242),
        "palette": [
            (39, 40, 34), (249, 38, 114), (166, 226, 46), (230, 219, 116),
            (102, 217, 239), (174, 129, 255), (161, 239, 228), (248, 248, 242),
            (117, 113, 94), (249, 38, 114), (166, 226, 46), (230, 219, 116),
            (102, 217, 239), (174, 129, 255), (161, 239, 228), (249, 248, 245),
        ],
    },
    "SolarizedDark": {
        "bg": (0, 43, 54), "fg": (131, 148, 150),
        "palette": [
            (7, 54, 66), (220, 50, 47), (133, 153, 0), (181, 137, 0),
            (38, 139, 210), (211, 54, 130), (42, 161, 152), (238, 232, 213),
            (0, 43, 54), (203, 75, 22), (88, 110, 117), (101, 123, 131),
            (131, 148, 150), (108, 113, 196), (147, 161, 161), (253, 246, 227),
        ],
    },
}


# ---------------------------------------------------------------------------
# Emulador de terminal ANSI mínimo
# ---------------------------------------------------------------------------

class Cell:
    __slots__ = ("ch", "fg", "bg", "bold")

    def __init__(self, ch=" ", fg=None, bg=None, bold=False):
        self.ch = ch
        self.fg = fg
        self.bg = bg
        self.bold = bold


CSI_RE = re.compile(r"\x1b\[([0-9;]*)([A-Za-z])")


class MiniTerminal:
    """Emulador de terminal ANSI muy simplificado: suficiente para bash,
    ls, echo, prompts con colores, git status, etc."""

    def __init__(self, cols, rows, theme):
        self.cols = cols
        self.rows = rows
        self.theme = theme
        self.cx = 0
        self.cy = 0
        self.cur_fg = None
        self.cur_bg = None
        self.cur_bold = False
        self.grid = [[Cell() for _ in range(cols)] for _ in range(rows)]
        self._buf = ""
        self.lock = threading.Lock()

    def _blank_row(self):
        return [Cell() for _ in range(self.cols)]

    def _scroll(self):
        self.grid.pop(0)
        self.grid.append(self._blank_row())

    def _put(self, ch):
        if self.cx >= self.cols:
            self.cx = 0
            self.cy += 1
            if self.cy >= self.rows:
                self._scroll()
                self.cy = self.rows - 1
        self.grid[self.cy][self.cx] = Cell(ch, self.cur_fg, self.cur_bg, self.cur_bold)
        self.cx += 1

    def _apply_sgr(self, params):
        if not params:
            params = [0]
        i = 0
        while i < len(params):
            p = params[i]
            if p == 0:
                self.cur_fg = None
                self.cur_bg = None
                self.cur_bold = False
            elif p == 1:
                self.cur_bold = True
            elif p == 22:
                self.cur_bold = False
            elif p == 39:
                self.cur_fg = None
            elif p == 49:
                self.cur_bg = None
            elif 30 <= p <= 37:
                self.cur_fg = p - 30
            elif 90 <= p <= 97:
                self.cur_fg = (p - 90) + 8
            elif 40 <= p <= 47:
                self.cur_bg = p - 40
            elif 100 <= p <= 107:
                self.cur_bg = (p - 100) + 8
            elif p == 38 and i + 2 < len(params) and params[i + 1] == 5:
                # 256-color foreground: aproximamos al índice de 16 colores
                self.cur_fg = params[i + 2] % 16
                i += 2
            elif p == 48 and i + 2 < len(params) and params[i + 1] == 5:
                self.cur_bg = params[i + 2] % 16
                i += 2
            i += 1

    def feed(self, data: bytes):
        text = data.decode("utf-8", errors="replace")
        with self.lock:
            self._feed_text(text)

    def _feed_text(self, text):
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]

            if ch == "\x1b" and i + 1 < n and text[i + 1] == "[":
                m = CSI_RE.match(text, i)
                if m:
                    params_str, final = m.groups()
                    params = [int(p) if p else 0 for p in params_str.split(";")] if params_str else []
                    self._handle_csi(params, final)
                    i = m.end()
                    continue
                else:
                    i += 1
                    continue

            if ch == "\r":
                self.cx = 0
            elif ch == "\n":
                self.cy += 1
                if self.cy >= self.rows:
                    self._scroll()
                    self.cy = self.rows - 1
            elif ch == "\b":
                if self.cx > 0:
                    self.cx -= 1
            elif ch == "\t":
                self.cx = min(self.cols - 1, ((self.cx // 8) + 1) * 8)
            elif ch in ("\x07", "\x00"):
                pass
            elif ch == "\x1b":
                pass  # escape suelto sin secuencia reconocida, ignorar
            else:
                self._put(ch)

            i += 1

    def _handle_csi(self, params, final):
        p0 = params[0] if params else None

        if final == "m":
            self._apply_sgr(params)
        elif final == "H" or final == "f":
            row = (params[0] if len(params) > 0 and params[0] else 1) - 1
            col = (params[1] if len(params) > 1 and params[1] else 1) - 1
            self.cy = max(0, min(self.rows - 1, row))
            self.cx = max(0, min(self.cols - 1, col))
        elif final == "A":
            self.cy = max(0, self.cy - (p0 or 1))
        elif final == "B":
            self.cy = min(self.rows - 1, self.cy + (p0 or 1))
        elif final == "C":
            self.cx = min(self.cols - 1, self.cx + (p0 or 1))
        elif final == "D":
            self.cx = max(0, self.cx - (p0 or 1))
        elif final == "K":
            mode = p0 or 0
            row = self.grid[self.cy]
            if mode == 0:
                for x in range(self.cx, self.cols):
                    row[x] = Cell()
            elif mode == 1:
                for x in range(0, self.cx + 1):
                    row[x] = Cell()
            elif mode == 2:
                self.grid[self.cy] = self._blank_row()
        elif final == "J":
            mode = p0 or 0
            if mode == 2 or mode == 3:
                self.grid = [self._blank_row() for _ in range(self.rows)]
                self.cx, self.cy = 0, 0
            elif mode == 0:
                for y in range(self.cy, self.rows):
                    self.grid[y] = self._blank_row()
            elif mode == 1:
                for y in range(0, self.cy):
                    self.grid[y] = self._blank_row()
        # otras secuencias (modo cursor visible, scroll region, etc.) se ignoran

    def snapshot(self):
        with self.lock:
            return [[Cell(c.ch, c.fg, c.bg, c.bold) for c in row] for row in self.grid]


# ---------------------------------------------------------------------------
# Renderer: grid de Cells -> imagen PIL
# ---------------------------------------------------------------------------

class Renderer:
    def __init__(self, cols, rows, font_size, theme):
        font_path = shutil.which("true") and "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
        if not font_path or not os.path.exists(font_path):
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
        self.font = ImageFont.truetype(font_path, font_size)
        self.font_bold = self.font  # DejaVuSansMono.ttf no trae bold embebido; se simula con relleno

        bbox = self.font.getbbox("M")
        self.char_w = self.font.getlength("M")
        self.line_h = int((bbox[3] - bbox[1]) * 1.5) + 4
        self.pad = 16
        self.cols = cols
        self.rows = rows
        self.theme = theme

        self.width = int(self.char_w * cols) + self.pad * 2
        self.height = self.line_h * rows + self.pad * 2

    def _color(self, idx, default):
        if idx is None:
            return default
        return self.theme["palette"][idx % 16]

    def render(self, grid):
        img = Image.new("RGB", (self.width, self.height), self.theme["bg"])
        draw = ImageDraw.Draw(img)

        for y, row in enumerate(grid):
            ypix = self.pad + y * self.line_h
            # agrupar celdas contiguas con mismo bg para pintar rectángulos rápido
            x = 0
            while x < len(row):
                cell = row[x]
                bg = self._color(cell.bg, self.theme["bg"])
                if bg != self.theme["bg"]:
                    x2 = x
                    while x2 < len(row) and self._color(row[x2].bg, self.theme["bg"]) == bg:
                        x2 += 1
                    xpix = self.pad + x * self.char_w
                    xpix2 = self.pad + x2 * self.char_w
                    draw.rectangle([xpix, ypix, xpix2, ypix + self.line_h], fill=bg)
                    x = x2
                else:
                    x += 1

            for x, cell in enumerate(row):
                if cell.ch == " ":
                    continue
                xpix = self.pad + x * self.char_w
                fg = self._color(cell.fg, self.theme["fg"])
                draw.text((xpix, ypix), cell.ch, font=self.font, fill=fg)
                if cell.bold:
                    draw.text((xpix + 0.6, ypix), cell.ch, font=self.font, fill=fg)

        return img


# ---------------------------------------------------------------------------
# Parser del .tape
# ---------------------------------------------------------------------------

def parse_duration(token):
    token = token.strip()
    if token.endswith("ms"):
        return float(token[:-2]) / 1000.0
    if token.endswith("s"):
        return float(token[:-1])
    return float(token)


def parse_tape(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    settings = {
        "Shell": "bash",
        "FontSize": 16,
        "Width": 1200,
        "Height": 640,
        "Theme": "Default",
        "TypingSpeed": 0.035,
        "Framerate": 12,
    }
    output = None
    steps = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        try:
            tokens = shlex.split(line, posix=True)
        except ValueError:
            continue
        if not tokens:
            continue

        cmd = tokens[0]

        if cmd == "Output":
            output = tokens[1]
        elif cmd == "Set":
            key, value = tokens[1], tokens[2]
            if key == "TypingSpeed":
                settings[key] = parse_duration(value)
            elif key in ("FontSize", "Width", "Height", "Framerate"):
                settings[key] = int(value)
            else:
                settings[key] = value
        elif cmd == "Type":
            steps.append(("type", tokens[1]))
        elif cmd == "Enter":
            steps.append(("key", "\r" * (int(tokens[1]) if len(tokens) > 1 else 1)))
        elif cmd == "Space":
            steps.append(("key", " " * (int(tokens[1]) if len(tokens) > 1 else 1)))
        elif cmd == "Tab":
            steps.append(("key", "\t" * (int(tokens[1]) if len(tokens) > 1 else 1)))
        elif cmd == "Backspace":
            steps.append(("key", "\x7f" * (int(tokens[1]) if len(tokens) > 1 else 1)))
        elif cmd == "Up":
            steps.append(("key", "\x1b[A" * (int(tokens[1]) if len(tokens) > 1 else 1)))
        elif cmd == "Down":
            steps.append(("key", "\x1b[B" * (int(tokens[1]) if len(tokens) > 1 else 1)))
        elif cmd == "Right":
            steps.append(("key", "\x1b[C" * (int(tokens[1]) if len(tokens) > 1 else 1)))
        elif cmd == "Left":
            steps.append(("key", "\x1b[D" * (int(tokens[1]) if len(tokens) > 1 else 1)))
        elif cmd == "Sleep":
            steps.append(("sleep", parse_duration(tokens[1])))
        elif cmd.startswith("Ctrl+"):
            letter = cmd.split("+", 1)[1].lower()
            code = chr(ord(letter) - ord("a") + 1)
            steps.append(("key", code))
        elif cmd == "Screenshot":
            steps.append(("screenshot", tokens[1]))
        else:
            # comando desconocido: se ignora silenciosamente
            pass

    if output is None:
        output = "output.gif"

    return settings, output, steps


# ---------------------------------------------------------------------------
# Sesión de grabación: pty + shell real + hilo lector + hilo grabador
# ---------------------------------------------------------------------------

class RecordingSession:
    def __init__(self, settings):
        self.settings = settings
        theme = THEMES.get(settings["Theme"], THEMES["Default"])

        self.renderer = Renderer(1, 1, settings["FontSize"], theme)  # solo para medir char size
        cols = max(20, int((settings["Width"] - self.renderer.pad * 2) / self.renderer.char_w))
        rows = max(5, int((settings["Height"] - self.renderer.pad * 2) / self.renderer.line_h))

        self.term = MiniTerminal(cols, rows, theme)
        self.renderer = Renderer(cols, rows, settings["FontSize"], theme)

        self.master_fd, self.slave_fd = pty.openpty()
        self._set_winsize(cols, rows)

        env = dict(os.environ)
        env["TERM"] = "xterm-256color"
        env["PS1"] = r"\[\033[36m\]➜  \[\033[32m\]\W\[\033[0m\] $ "

        self.proc = subprocess.Popen(
            [settings["Shell"]],
            stdin=self.slave_fd,
            stdout=self.slave_fd,
            stderr=self.slave_fd,
            env=env,
            preexec_fn=os.setsid,
            close_fds=True,
        )
        os.close(self.slave_fd)

        self.frames = []
        self._stop = False
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._recorder_thread = threading.Thread(target=self._record_loop, daemon=True)

    def _set_winsize(self, cols, rows):
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

    def _read_loop(self):
        while not self._stop:
            try:
                r, _, _ = select.select([self.master_fd], [], [], 0.05)
                if self.master_fd in r:
                    data = os.read(self.master_fd, 65536)
                    if not data:
                        break
                    self.term.feed(data)
            except OSError:
                break

    def _record_loop(self):
        interval = 1.0 / max(1, self.settings["Framerate"])
        while not self._stop:
            img = self.renderer.render(self.term.snapshot())
            self.frames.append(img)
            time.sleep(interval)

    def start(self):
        self._reader_thread.start()
        self._recorder_thread.start()

    def send(self, text):
        os.write(self.master_fd, text.encode("utf-8"))

    def type_text(self, text):
        speed = self.settings["TypingSpeed"]
        for ch in text:
            os.write(self.master_fd, ch.encode("utf-8"))
            time.sleep(speed)

    def screenshot(self, path):
        img = self.renderer.render(self.term.snapshot())
        img.save(path)

    def stop(self):
        time.sleep(0.4)  # dejar que salga el último output
        self._stop = True
        self._reader_thread.join(timeout=1)
        self._recorder_thread.join(timeout=1)
        try:
            self.proc.terminate()
        except Exception:
            pass
        try:
            os.close(self.master_fd)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Exportado (GIF nativo con Pillow, mp4/webm con ffmpeg si está disponible)
# ---------------------------------------------------------------------------

def export(frames, output_path, framerate):
    if not frames:
        print("⚠ No se capturó ningún frame.")
        return

    ext = os.path.splitext(output_path)[1].lower()
    duration_ms = int(1000 / max(1, framerate))

    if ext == ".gif":
        frames[0].save(
            output_path,
            save_all=True,
            append_images=frames[1:],
            duration=duration_ms,
            loop=0,
            optimize=True,
        )
        print(f"✓ GIF exportado: {output_path} ({len(frames)} frames)")
        return

    if ext in (".mp4", ".webm"):
        if not shutil.which("ffmpeg"):
            fallback = os.path.splitext(output_path)[0] + ".gif"
            print(f"⚠ No se encontró ffmpeg. Exportando como GIF a {fallback} en su lugar.")
            export(frames, fallback, framerate)
            return

        tmp_dir = output_path + "_frames_tmp"
        os.makedirs(tmp_dir, exist_ok=True)
        for i, frame in enumerate(frames):
            frame.save(os.path.join(tmp_dir, f"frame_{i:05d}.png"))

        codec = ["-c:v", "libvpx-vp9"] if ext == ".webm" else ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        cmd = [
            "ffmpeg", "-y", "-framerate", str(framerate),
            "-i", os.path.join(tmp_dir, "frame_%05d.png"),
            *codec, output_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"✓ Video exportado: {output_path} ({len(frames)} frames)")
        return

    # extensión desconocida -> gif por default
    fallback = output_path + ".gif"
    export(frames, fallback, framerate)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_tape(tape_path):
    if sys.platform.startswith("win"):
        print("✖ RecoveryWorld necesita pty (Linux/macOS). En Windows probá WSL.")
        sys.exit(1)

    settings, output_path, steps = parse_tape(tape_path)

    print(f"🟧 RecoveryWorld — grabando '{tape_path}' → {output_path}")
    session = RecordingSession(settings)
    session.start()

    time.sleep(0.6)  # esperar a que el shell muestre el prompt inicial

    for kind, value in steps:
        if kind == "type":
            session.type_text(value)
        elif kind == "key":
            session.send(value)
        elif kind == "sleep":
            time.sleep(value)
        elif kind == "screenshot":
            session.screenshot(value)
            print(f"  📸 screenshot guardado: {value}")

    session.stop()
    export(session.frames, output_path, settings["Framerate"])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python3 recoveryworld.py archivo.tape")
        sys.exit(1)

    run_tape(sys.argv[1])
