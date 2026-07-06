<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,15,20&height=220&section=header&text=RecoveryWorld&fontSize=60&fontColor=ffffff&animation=fadeIn&fontAlignY=35&desc=Grabá%20tu%20terminal%20como%20GIF%2C%20sin%20depender%20de%20nada%20externo&descAlignY=55&descSize=18" width="100%" />

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=22&pause=1000&color=BD93F9&center=true&vCenter=true&width=650&lines=Escribí+un+.tape%2C+obtené+un+GIF;pty+real+%2B+emulador+ANSI+casero;GIF%2C+MP4+o+WebM+de+salida;Cero+dependencias+pesadas." alt="Typing SVG" />

<br/>

![Python](https://img.shields.io/badge/python-3.10%2B-purple?style=for-the-badge&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macos-blueviolet?style=for-the-badge&logo=linux&logoColor=white)
![Pillow](https://img.shields.io/badge/deps-Pillow-orange?style=for-the-badge&logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-lightgrey?style=for-the-badge)
![Status](https://img.shields.io/badge/status-en%20desarrollo-yellow?style=for-the-badge)

</div>

---

## 🟪 ¿Qué es RecoveryWorld?

**RecoveryWorld** es un clon simplificado de [VHS](https://github.com/charmbracelet/vhs), escrito en
Python puro. Le das un script `.tape` con instrucciones tipo "escribí esto", "esperá tanto",
"apretá Enter" — y te devuelve un **GIF (o MP4/WebM)** grabando una terminal real actuando ese guion,
tipeo incluido.

No depende de navegadores headless ni de Go: abre un **pty real**, corre tu shell adentro, interpreta
la salida con un emulador ANSI hecho a mano, y renderiza cada frame con Pillow.

<div align="center">

<img src="demo.gif" alt="Demo de RecoveryWorld" width="80%" />

</div>

> 💡 El GIF de arriba (`demo.gif`) fue generado corriendo `demo.tape` — no es un mockup, es el output real del script.

---

## ✨ Features

| | |
|---|---|
| 📼 **Scripting tipo VHS** | `Output`, `Set`, `Type`, `Enter`, `Sleep`, `Ctrl+X`, `Screenshot`, flechas, `Tab`, `Backspace` |
| 🖥️ **pty real** | Corre tu shell de verdad (`bash`, `zsh`, `fish`...), no un simulacro |
| 🎨 **Emulador ANSI propio** | Colores SGR, movimiento de cursor, scroll, erase — sin depender de `pyte` ni librerías de terminal |
| 🌈 **Temas incluidos** | `Default`, `Dracula`, `Monokai`, `SolarizedDark` |
| 🎞️ **Export flexible** | `.gif` nativo con Pillow; `.mp4` / `.webm` vía `ffmpeg` si está instalado (si no, cae a GIF automáticamente) |
| ⌨️ **Tipeo animado** | `TypingSpeed` configurable, letra por letra, como una persona escribiendo de verdad |

---

## 📦 Instalación

```bash
pip install pillow
# opcional, para exportar a mp4/webm:
# sudo apt install ffmpeg
```

Sólo Linux/macOS (usa `pty` de la stdlib). En Windows, corré esto desde WSL.

## 🚀 Uso

```bash
python3 recoveryworld.py demo.tape
```

### Ejemplo de `.tape`

```tape
Output demo.gif
Set Shell "bash"
Set FontSize 18
Set Width 1000
Set Height 500
Set Theme "Dracula"
Set TypingSpeed 40ms
Set Framerate 12

Type "echo Hola RecoveryWorld"
Enter
Sleep 1s
Type "ls -la"
Enter
Sleep 1.5s
```

### Comandos soportados

| Comando | Qué hace |
|---|---|
| `Output <archivo>` | Ruta de salida (`.gif`, `.mp4`, `.webm`) |
| `Set <Clave> <Valor>` | `Shell`, `FontSize`, `Width`, `Height`, `Theme`, `TypingSpeed`, `Framerate` |
| `Type "texto"` | Escribe el texto letra por letra |
| `Enter` / `Space` / `Tab` / `Backspace` | Teclas especiales (aceptan un número opcional de repeticiones) |
| `Up` / `Down` / `Left` / `Right` | Flechas del teclado |
| `Ctrl+<letra>` | Combinación de control, ej. `Ctrl+C` |
| `Sleep <duración>` | Pausa, ej. `1s`, `500ms` |
| `Screenshot <archivo.png>` | Captura un frame puntual como imagen |

---

## ⚠️ Limitaciones

RecoveryWorld usa un emulador de terminal ANSI **mínimo, escrito a mano** (no `pyte` ni un xterm
completo), así que:

- Cubre bien lo típico: `bash`, `ls`, `echo`, prompts con color, `git status`, etc.
- Cosas más exóticas (256 colores exactos, unicode de ancho doble, soporte de mouse) pueden no
  verse perfectas.
- El "bold" se simula dibujando el texto dos veces desplazado, porque la fuente por defecto
  (DejaVu Sans Mono) no trae una variante bold embebida.

---

## 🗺️ Roadmap

- [ ] Comandos `Hide` / `Show` (ocultar el cursor durante ciertos tramos)
- [ ] `Set Padding` y `Set CursorBlink`
- [ ] Soporte de fuentes bold reales (pasar una ruta de `-Bold.ttf`)
- [ ] Modo "grabar sesión interactiva" (grabar lo que vos tipeás en vivo, no solo un script)

---

## 🤝 Contribuir

PRs bienvenidos. Si encontrás un caso donde el render ANSI se rompe, un `.tape` de ejemplo que lo
reproduzca ayuda muchísimo a arreglarlo.

## 📄 Licencia

MIT — usalo, rompelo, mejoralo.

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,15,20&height=100&section=footer" width="100%" />

</div>
