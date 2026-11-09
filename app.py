"""
הקורא העברי (HebrewReader) - הקראת טקסט בעברית, מקומית לגמרי ובלי אינטרנט. חינם, מ-ZombieStar Studio.

שני קולות: "קול בסיסי" (StyleTTS2, engine.py, מהיר בכל מחשב) ו"תאיר" (ZipVoice, zip_engine.py, טבעי ואיטי במעבד).
הטקסט לא יוצא מהמחשב: אין כאן שום קריאה לרשת.
"""

from __future__ import annotations

import os
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import paths
from engine import dominant_script

APP_TITLE = "הקורא העברי"
APP_VERSION = "1.0.0"

VOICE_BASIC = "קול בסיסי (מהיר, כל מחשב)"
VOICE_TAIR = "תאיר (טבעי, מחשב חזק)"


def tair_available() -> bool:
    """The voice תאיר is a separate pack (models/zipvoice + voices/tair.*): it is listed only when it is there."""
    import importlib.util

    if importlib.util.find_spec("zipvoice_onnx") is None or importlib.util.find_spec("zip_engine") is None:
        return False  # the public build leaves the engine out
    return (paths.MODELS / "zipvoice" / "fm_decoder_int8.onnx").is_file() and (paths.VOICES / "tair.wav").is_file()


VOICES = {VOICE_BASIC: "basic", **({VOICE_TAIR: "tair"} if tair_available() else {})}
# Measured on the CPU, int8 decoder, 4 threads (README, "the voice תאיר"): the honest number goes in the hint.
TAIR_SECONDS_PER_SECOND = "2 עד 2.5"
TAIR_HINT = (
    "תאיר: קול טבעי, אבל במחשב בלי כרטיס מסך הוא איטי - בערך {x} שניות הכנה לכל שנייה של דיבור, "
    "ולכן יש הפסקות קצרות בין משפטים. לטקסט ארוך אפשר לשמור WAV ולשמוע אחר כך. הקול הבסיסי מהיר בכל מחשב."
)

PACES = {"איטי": "slow", "רגיל": "normal", "מהיר": "fast"}
SPEEDS = {
    "basic": {"slow": 0.95, "normal": 1.12, "fast": 1.35},
    "tair": {"slow": 0.92, "normal": 1.0, "fast": 1.2},
}
FONT_SIZES = (12, 14, 16, 18, 20, 24, 28, 32)

MAX_CHUNK_CHARS = 180
SILENCE_BETWEEN_CHUNKS = 0.20  # שניות - נשימה בין משפטים

# מקשי הצירוף מזוהים לפי קוד החומרה ולא לפי האות, כדי שההדבקה תעבוד
# גם כשהמקלדת במצב עברית ו-Ctrl+V שולח את האות ה.
KEYCODE_A, KEYCODE_C, KEYCODE_V, KEYCODE_X = 65, 67, 86, 88

PALETTE = {
    "bg": "#EEF1F6",
    "card": "#FFFFFF",
    "border": "#D3D9E3",
    "text": "#161A20",
    "muted": "#6B7484",
    "accent": "#2F6FED",
    "accent_hover": "#255CD1",
    "accent_text": "#FFFFFF",
    "button": "#E4E8F0",
    "button_hover": "#D6DCE8",
    "selection": "#C7D9FF",
}


def split_to_chunks(text: str) -> list[str]:
    """מפצל טקסט למקטעים קצרים לפי פיסוק, כדי שההקראה תתחיל מהר ותישמע טבעית."""
    text = re.sub(r"[ \t]+", " ", text.strip())
    if not text:
        return []

    sentences = [
        s.strip() for s in re.split(r"(?<=[.!?…:;])\s+|\n+", text) if s and s.strip()
    ]

    pieces: list[str] = []
    for sentence in sentences:
        if len(sentence) <= MAX_CHUNK_CHARS:
            pieces.append(sentence)
            continue
        # משפט ארוך מדי - מפצלים לפי פסיקים ואז לפי רווחים
        buf = ""
        for part in re.split(r"(?<=,)\s+", sentence):
            while len(part) > MAX_CHUNK_CHARS:
                cut = part.rfind(" ", 0, MAX_CHUNK_CHARS)
                cut = cut if cut > 0 else MAX_CHUNK_CHARS
                pieces.append(part[:cut].strip())
                part = part[cut:].strip()
            if len(buf) + len(part) + 1 > MAX_CHUNK_CHARS:
                if buf:
                    pieces.append(buf.strip())
                buf = part
            else:
                buf = f"{buf} {part}".strip()
        if buf:
            pieces.append(buf.strip())

    # איחוד מקטעים קצרים לשכנים שלהם, בלי לערבב שפות באותו מקטע
    merged: list[str] = []
    for piece in pieces:
        if (
            merged
            and len(merged[-1]) + len(piece) + 1 <= MAX_CHUNK_CHARS
            and dominant_script(merged[-1]) == dominant_script(piece)
        ):
            merged[-1] = f"{merged[-1]} {piece}"
        else:
            merged.append(piece)
    return merged


class Speech:
    """Two local engines, each loaded only when its voice is first used."""

    def __init__(self) -> None:
        self._basic = None
        self._tair = None

    def engine(self, voice: str):
        if voice == "tair":
            if self._tair is None:
                from zip_engine import ZipEngine

                self._tair = ZipEngine()
            return self._tair
        if self._basic is None:
            from engine import Engine

            self._basic = Engine()
        return self._basic

    def ensure_loaded(self, voice: str, on_status=None) -> None:
        engine = self.engine(voice)
        if voice == "tair":
            if on_status and engine._model is None:
                on_status("טוען את הקול תאיר, רק בפעם הראשונה...")
            engine.ensure_loaded()
        else:
            engine.ensure_loaded(on_status)

    def chunks(self, text: str) -> list[str]:
        return split_to_chunks(text)

    def synthesize(self, chunk: str, voice: str, pace: str):
        return self.engine(voice).synthesize(chunk, SPEEDS[voice][pace])


def _dpi_aware() -> None:
    """Sharp text on scaled Windows screens (125%, 150%): without it Windows stretches a blurry bitmap."""
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def log_dir() -> Path:
    """%LOCALAPPDATA%\\HebrewReader: the app folder may be read-only (Program Files, a school share)."""
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "HebrewReader"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return root


def _span_index(spans: list[tuple[str, float, float]], elapsed: float) -> int:
    """איזו מילה אמורה להישמע כרגע, לפי הזמן שעבר מתחילת המקטע."""
    for index, (_word, start, end) in enumerate(spans):
        if start <= elapsed < end:
            return index
    return len(spans) - 1 if spans and elapsed >= spans[-1][2] else -1


class App(tk.Tk):
    def __init__(self, initial_text: str | None = None) -> None:
        _dpi_aware()
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("920x680")
        self.minsize(640, 480)
        self.configure(background=PALETTE["bg"])

        self.engine = Speech()
        self._stop_flag = threading.Event()
        self._worker: threading.Thread | None = None

        # מצב המשך: מאיזה מקטע לחדש, ומאיפה בטקסט להמשיך לסמן
        self._resume_index = 0
        self._resume_search_pos = "1.0"
        self._search_pos = "1.0"
        self._chunk_start_pos = "1.0"
        self._current_index = 0

        self._font_size = 16
        self._set_icon()
        self._build_style()
        self._build_ui()
        if initial_text:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", initial_text)
            self._apply_rtl()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- עיצוב ----------

    def _set_icon(self) -> None:
        import sys

        for candidate in (paths.BASE / "icon.ico", Path(getattr(sys, "_MEIPASS", paths.BASE)) / "icon.ico"):
            if candidate.is_file():
                try:
                    self.iconbitmap(default=str(candidate))
                except tk.TclError:
                    pass
                return

    def _build_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("TFrame", background=PALETTE["bg"])

        style.configure(
            "Title.TLabel",
            background=PALETTE["bg"],
            foreground=PALETTE["text"],
            font=("Segoe UI Semibold", 17),
        )
        style.configure(
            "Subtitle.TLabel",
            background=PALETTE["bg"],
            foreground=PALETTE["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Status.TLabel",
            background=PALETTE["bg"],
            foreground=PALETTE["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Field.TLabel",
            background=PALETTE["bg"],
            foreground=PALETTE["text"],
            font=("Segoe UI", 10),
        )

        style.configure(
            "Secondary.TButton",
            background=PALETTE["button"],
            foreground=PALETTE["text"],
            font=("Segoe UI", 10),
            borderwidth=0,
            focusthickness=0,
            padding=(14, 9),
        )
        style.map(
            "Secondary.TButton",
            background=[
                ("active", PALETTE["button_hover"]),
                ("disabled", PALETTE["bg"]),
            ],
            foreground=[("disabled", PALETTE["muted"])],
        )

        style.configure(
            "Primary.TButton",
            background=PALETTE["accent"],
            foreground=PALETTE["accent_text"],
            font=("Segoe UI Semibold", 11),
            borderwidth=0,
            focusthickness=0,
            padding=(24, 10),
        )
        style.map(
            "Primary.TButton",
            background=[
                ("active", PALETTE["accent_hover"]),
                ("disabled", PALETTE["button"]),
            ],
            foreground=[("disabled", PALETTE["muted"])],
        )

        style.configure(
            "Speed.Horizontal.TScale",
            background=PALETTE["bg"],
            troughcolor=PALETTE["button"],
            borderwidth=0,
            lightcolor=PALETTE["accent"],
            darkcolor=PALETTE["accent"],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=PALETTE["button"],
            troughcolor=PALETTE["card"],
            borderwidth=0,
            arrowsize=12,
        )

    # ---------- ממשק ----------

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=(20, 16, 20, 14))
        root.pack(fill="both", expand=True)

        head = ttk.Frame(root)
        head.pack(fill="x", pady=(0, 12))
        ttk.Button(head, text="אודות", style="Secondary.TButton", command=self.on_about).pack(side="left", anchor="n")
        ttk.Label(head, text=APP_TITLE, style="Title.TLabel").pack(anchor="e")
        self.subtitle = ttk.Label(
            head,
            text="מדביקים טקסט ולוחצים הקרא. הטקסט לא יוצא מהמחשב.",
            style="Subtitle.TLabel",
        )
        self.subtitle.pack(anchor="e", pady=(2, 0))

        card = tk.Frame(
            root,
            background=PALETTE["card"],
            highlightbackground=PALETTE["border"],
            highlightthickness=1,
            bd=0,
        )
        # packed last (below): the bottom rows must keep their place when the window is short

        scroll = ttk.Scrollbar(card, orient="vertical", style="Vertical.TScrollbar")
        scroll.pack(side="left", fill="y", padx=(6, 0), pady=6)

        self.text = tk.Text(
            card,
            wrap="word",
            font=("Segoe UI", self._font_size),
            undo=True,
            maxundo=200,
            padx=16,
            pady=14,
            background=PALETTE["card"],
            foreground=PALETTE["text"],
            insertbackground=PALETTE["accent"],
            selectbackground=PALETTE["selection"],
            selectforeground=PALETTE["text"],
            spacing1=2,
            spacing3=6,
            relief="flat",
            highlightthickness=0,
            borderwidth=0,
            yscrollcommand=scroll.set,
        )
        self.text.pack(side="right", fill="both", expand=True)
        scroll.config(command=self.text.yview)

        self.text.tag_configure("rtl", justify="right")

        # Tk has no bidi engine: a tag applied to part of a line splits that
        # line into separate display chunks, and the chunks are then laid out
        # left to right, which reverses Hebrew. So the reading marker is not a
        # tag at all - it is a bar placed under the word, leaving the text one
        # unbroken run.
        self.marker = tk.Frame(self.text, background=PALETTE["accent"], height=3)
        self.text.bind("<<Modified>>", self._apply_rtl)
        self.text.bind("<KeyRelease>", self._apply_rtl)
        self.text.insert(
            "1.0",
            "שלום! הדביקו כאן טקסט ולחצו הקרא. הקורא יודע לקרוא גם מספרים, כמו 3 ספרים ו-12 מחברות.",
        )
        self._apply_rtl()

        self._build_context_menu()

        controls = ttk.Frame(root)


        self.play_btn = ttk.Button(
            controls, text="הקרא", style="Primary.TButton", command=self.on_play
        )
        self.play_btn.pack(side="right")

        self.stop_btn = ttk.Button(
            controls,
            text="עצור",
            style="Secondary.TButton",
            command=self.on_stop,
            state="disabled",
        )
        self.stop_btn.pack(side="right", padx=8)

        self.restart_btn = ttk.Button(
            controls,
            text="מהתחלה",
            style="Secondary.TButton",
            command=self.on_restart,
        )
        self.restart_btn.pack(side="right", padx=(0, 8))

        ttk.Button(
            controls, text="הדבק", style="Secondary.TButton", command=self.on_paste
        ).pack(side="right", padx=(0, 8))

        self.save_btn = ttk.Button(
            controls, text="שמור WAV", style="Secondary.TButton", command=self.on_save
        )
        self.save_btn.pack(side="right", padx=(0, 8))

        ttk.Button(
            controls, text="נקה", style="Secondary.TButton", command=self.on_clear
        ).pack(side="right", padx=(0, 8))

        picker = ttk.Frame(root)  # its own row: voice, pace and text size

        # right to left: each label sits to the right of its field
        ttk.Label(picker, text="קול", style="Field.TLabel").pack(side="right", padx=(0, 6))
        self.voice_var = tk.StringVar(value=VOICE_BASIC)
        voice_box = ttk.Combobox(
            picker,
            textvariable=self.voice_var,
            values=list(VOICES),
            state="readonly",
            width=26,
            justify="right",
            font=("Segoe UI", 10),
        )
        voice_box.pack(side="right")
        voice_box.bind("<<ComboboxSelected>>", self._on_voice)

        ttk.Label(picker, text="קצב", style="Field.TLabel").pack(side="right", padx=(22, 6))
        self.pace_var = tk.StringVar(value="רגיל")
        ttk.Combobox(
            picker,
            textvariable=self.pace_var,
            values=list(PACES),
            state="readonly",
            width=7,
            justify="right",
            font=("Segoe UI", 10),
        ).pack(side="right")

        ttk.Label(picker, text="גודל הטקסט", style="Field.TLabel").pack(side="right", padx=(22, 6))
        ttk.Button(picker, text="+", width=3, style="Secondary.TButton", command=lambda: self._zoom(1)).pack(side="right")
        ttk.Button(picker, text="-", width=3, style="Secondary.TButton", command=lambda: self._zoom(-1)).pack(
            side="right", padx=(4, 0)
        )

        self.hint = ttk.Label(root, text="", style="Status.TLabel", anchor="e", justify="right", wraplength=860)

        footer = ttk.Frame(root)
        footer.pack(side="bottom", fill="x", pady=(6, 0))
        self.hint.pack(side="bottom", fill="x", pady=(8, 0))
        controls.pack(side="bottom", fill="x", pady=(12, 0))
        picker.pack(side="bottom", fill="x", pady=(12, 0))
        card.pack(fill="both", expand=True)
        self.status = ttk.Label(footer, text="מוכן", style="Status.TLabel", anchor="e")
        self.status.pack(side="right")

    def _build_context_menu(self) -> None:
        menu = tk.Menu(self, tearoff=0, font=("Segoe UI", 10))
        menu.add_command(label="הדבק", command=self.on_paste)
        menu.add_command(label="העתק", command=lambda: self._clipboard("<<Copy>>"))
        menu.add_command(label="גזור", command=lambda: self._clipboard("<<Cut>>"))
        menu.add_separator()
        menu.add_command(label="בחר הכל", command=self._select_all)
        menu.add_command(label="נקה", command=self.on_clear)
        self._menu = menu
        self.text.bind("<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event) -> str:
        self.text.focus_set()
        self._menu.tk_popup(event.x_root, event.y_root)
        return "break"

    # ---------- קריאה מהלוח מכל מקום ----------

    def _on_voice(self, _event=None) -> None:
        if VOICES[self.voice_var.get()] == "tair":
            self.hint.config(text=TAIR_HINT.format(x=TAIR_SECONDS_PER_SECOND))
        else:
            self.hint.config(text="")

    def _zoom(self, step: int) -> None:
        sizes = list(FONT_SIZES)
        index = min(range(len(sizes)), key=lambda i: abs(sizes[i] - self._font_size))
        self._font_size = sizes[max(0, min(len(sizes) - 1, index + step))]
        self.text.configure(font=("Segoe UI", self._font_size))
        self._clear_highlight()

    def on_about(self) -> None:
        window = tk.Toplevel(self)
        window.title("אודות - " + APP_TITLE)
        window.configure(background=PALETTE["bg"])
        window.transient(self)
        window.geometry("680x560")
        body = ttk.Frame(window, padding=(18, 14))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"{APP_TITLE} {APP_VERSION}", style="Title.TLabel").pack(anchor="e")
        ttk.Label(body, text="חינם, מ-ZombieStar Studio", style="Subtitle.TLabel").pack(anchor="e", pady=(2, 8))
        box = tk.Text(body, wrap="word", font=("Segoe UI", 10), background=PALETTE["card"], foreground=PALETTE["text"],
                      relief="flat", padx=12, pady=10, highlightthickness=1, highlightbackground=PALETTE["border"])
        box.pack(fill="both", expand=True)
        credits = paths.BASE / "CREDITS.txt"
        text = credits.read_text(encoding="utf-8") if credits.is_file() else "CREDITS.txt is missing."
        box.insert("1.0", text)
        box.configure(state="disabled")
        ttk.Button(body, text="סגור", style="Secondary.TButton", command=window.destroy).pack(anchor="w", pady=(10, 0))

    def read_clipboard(self) -> None:
        """מדביק את תוכן הלוח ומתחיל להקריא אותו מיד."""
        try:
            clip = self.clipboard_get()
        except tk.TclError:
            self.set_status("אין טקסט בלוח")
            return
        if not clip.strip():
            self.set_status("אין טקסט בלוח")
            return
        if self._worker and self._worker.is_alive():
            self.on_stop()
        self.text.delete("1.0", "end")
        self.text.insert("1.0", clip)
        self._apply_rtl()
        self._reset_progress()
        self.on_play()

    def _on_close(self) -> None:
        self._stop_flag.set()
        self.destroy()

    def _bind_shortcuts(self) -> None:
        self.text.bind("<Control-KeyPress>", self._on_control_key)
        self.bind("<Control-Shift-V>", lambda _: self.read_clipboard())
        self.bind("<Control-Return>", lambda _: self.on_play())
        self.bind("<Escape>", lambda _: self.on_stop())

    def _on_control_key(self, event) -> str | None:
        """מטפל בהעתק והדבק לפי קוד המקש, כדי שזה יעבוד גם במקלדת עברית."""
        actions = {
            KEYCODE_V: self.on_paste,
            KEYCODE_C: lambda: self._clipboard("<<Copy>>"),
            KEYCODE_X: lambda: self._clipboard("<<Cut>>"),
            KEYCODE_A: self._select_all,
        }
        action = actions.get(event.keycode)
        if action is None:
            return None
        action()
        return "break"

    def _clipboard(self, virtual_event: str) -> None:
        self.text.event_generate(virtual_event)

    def _select_all(self) -> None:
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "1.0")

    def _apply_rtl(self, _event=None) -> None:
        self.text.tag_add("rtl", "1.0", "end")
        self.text.edit_modified(False)

    # ---------- סימון המילה המוקראת ----------

    def _highlight(self, word: str) -> None:
        index = self.text.search(word, self._search_pos, stopindex="end")
        if not index:
            return
        end = f"{index}+{len(word)}c"
        self._search_pos = end
        self.text.see(index)
        self.text.update_idletasks()
        self._place_marker(index, f"{end}-1c")

    def _place_marker(self, start: str, last: str) -> None:
        """Underline the word being spoken, using screen coordinates only."""
        head = self.text.bbox(start)
        tail = self.text.bbox(last)
        if head is None or tail is None:
            self.marker.place_forget()
            return
        hx, hy, hw, hh = head
        tx, ty, tw, th = tail
        if abs(hy - ty) > 2:  # the word wrapped - underline the first part only
            tx, ty, tw, th = hx, hy, hw, hh
        left = min(hx, tx)
        width = max(hx + hw, tx + tw) - left
        top = max(hy + hh, ty + th) - 1
        self.marker.place(x=left, y=top, width=max(width, 4))
        self.marker.lift()

    def _clear_highlight(self) -> None:
        self.marker.place_forget()

    def _mark_chunk_start(self, index: int) -> None:
        self._current_index = index
        self._chunk_start_pos = self._search_pos

    def _reset_progress(self) -> None:
        """מבטל את נקודת ההמשך - נקרא כשהטקסט השתנה או שההקראה הסתיימה."""
        self._resume_index = 0
        self._resume_search_pos = "1.0"
        self._search_pos = "1.0"
        self._chunk_start_pos = "1.0"
        self._current_index = 0
        self.play_btn.config(text="הקרא")

    def set_status(self, message: str) -> None:
        self.after(0, lambda: self.status.config(text=message))

    def _busy(self, busy: bool) -> None:
        def apply() -> None:
            self.play_btn.config(state="disabled" if busy else "normal")
            self.save_btn.config(state="disabled" if busy else "normal")
            self.stop_btn.config(state="normal" if busy else "disabled")

        self.after(0, apply)

    def _get_text(self) -> str:
        return self.text.get("1.0", "end").strip()

    # ---------- פעולות ----------

    def on_paste(self) -> None:
        """מדביק מהלוח, ומחליף את הבחירה הנוכחית אם יש כזו."""
        try:
            clip = self.clipboard_get()
        except tk.TclError:
            self.set_status("אין טקסט בלוח")
            return
        try:
            self.text.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        self.text.insert("insert", clip)
        self._apply_rtl()
        self.text.see("insert")
        self.set_status("הודבק מהלוח")

    def on_clear(self) -> None:
        self.text.delete("1.0", "end")
        self._reset_progress()
        self.set_status("מוכן")

    def on_stop(self) -> None:
        if not (self._worker and self._worker.is_alive()):
            return
        self._stop_flag.set()
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:
            pass
        # מחדשים מתחילת המקטע שנקטע, כדי לא לחתוך משפט באמצע
        self._resume_index = max(0, self._current_index - 1)
        self._resume_search_pos = self._chunk_start_pos
        self.play_btn.config(text="המשך")
        self.set_status("נעצר - אפשר להמשיך מכאן")

    def on_play(self, from_start: bool = False) -> None:
        if self._worker and self._worker.is_alive():
            return
        text = self._get_text()
        if not text:
            self.set_status("אין טקסט להקראה")
            return
        if from_start:
            self._reset_progress()
        start_index = self._resume_index
        self._search_pos = self._resume_search_pos
        self._clear_highlight()
        self._stop_flag.clear()
        self._busy(True)
        self._worker = threading.Thread(
            target=self._play_worker, args=(text, start_index), daemon=True
        )
        self._worker.start()

    def on_restart(self) -> None:
        self.on_play(from_start=True)

    def on_save(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        text = self._get_text()
        if not text:
            self.set_status("אין טקסט לשמירה")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".wav",
            filetypes=[("קובץ שמע WAV", "*.wav")],
            initialfile="speech.wav",
        )
        if not path:
            return
        self._stop_flag.clear()
        self._busy(True)
        self._worker = threading.Thread(
            target=self._save_worker, args=(text, path), daemon=True
        )
        self._worker.start()

    # ---------- עבודה ברקע ----------

    def _prepare(self) -> tuple[str, str]:
        voice, pace = VOICES[self.voice_var.get()], PACES[self.pace_var.get()]
        self.engine.ensure_loaded(voice, self.set_status)
        return voice, pace

    def _play_worker(self, text: str, start_index: int = 0) -> None:
        try:
            import numpy as np
            import sounddevice as sd

            voice, pace = self._prepare()
            chunks = self.engine.chunks(text)
            if not chunks:
                self.set_status("אין טקסט להקראה")
                return
            start_index = min(start_index, len(chunks) - 1)

            audio_queue: queue.Queue = queue.Queue(maxsize=2)
            errors: list[str] = []

            def producer() -> None:
                for index, chunk in enumerate(chunks[start_index:], start=start_index + 1):
                    if self._stop_flag.is_set():
                        break
                    try:
                        samples, sr, spans = self.engine.synthesize(chunk, voice, pace)
                    except Exception as exc:  # מקטע בעייתי לא יפיל את כל ההקראה
                        print(f"chunk {index} failed: {exc}")
                        errors.append(str(exc))
                        continue
                    if samples is None:
                        continue
                    audio_queue.put((index, samples, sr, spans))
                audio_queue.put(None)

            threading.Thread(target=producer, daemon=True).start()

            total = len(chunks)
            gap = None
            finished = True
            spoken_anything = False
            if voice == "tair":
                self.set_status("תאיר מכין את המשפט הראשון...")
            while not self._stop_flag.is_set():
                item = audio_queue.get()
                if item is None:
                    break
                index, samples, sr, spans = item
                spoken_anything = True
                if gap is None:
                    gap = np.zeros(int(sr * SILENCE_BETWEEN_CHUNKS), dtype="float32")
                self.after(0, self._mark_chunk_start, index)
                self.set_status(f"מקריא... מקטע {index} מתוך {total}")
                sd.play(np.concatenate([samples.astype("float32"), gap]), sr)

                started = time.monotonic()
                spoken = -1
                while sd.get_stream().active:
                    if self._stop_flag.is_set():
                        sd.stop()
                        finished = False
                        break
                    elapsed = time.monotonic() - started
                    current = _span_index(spans, elapsed)
                    if current != spoken:
                        spoken = current
                        if current >= 0:
                            self.after(0, self._highlight, spans[current][0])
                    sd.sleep(20)

            if errors and not spoken_anything:
                message = errors[0]
                self.after(0, lambda: messagebox.showerror("שגיאה בהקראה", message))
            if finished and not self._stop_flag.is_set():
                self.after(0, self._clear_highlight)
                self.after(0, self._reset_progress)
                self.set_status("סיים")
        except FileNotFoundError as exc:
            self.set_status("שגיאה")
            self.after(0, lambda: messagebox.showerror("קבצים חסרים", str(exc)))
        except Exception as exc:
            self.set_status("שגיאה")
            message = str(exc)
            self.after(0, lambda: messagebox.showerror("שגיאה בהקראה", message))
        finally:
            self._busy(False)

    def _save_worker(self, text: str, path: str) -> None:
        try:
            import numpy as np
            import soundfile as sf

            voice, pace = self._prepare()
            chunks = self.engine.chunks(text)
            parts: list = []
            sample_rate = 24000
            for index, chunk in enumerate(chunks, start=1):
                if self._stop_flag.is_set():
                    self.set_status("השמירה בוטלה")
                    return
                self.set_status(f"מייצר שמע... {index} מתוך {len(chunks)}")
                samples, sample_rate, _ = self.engine.synthesize(chunk, voice, pace)
                if samples is None:
                    continue
                parts.append(samples.astype("float32"))
                parts.append(
                    np.zeros(int(sample_rate * SILENCE_BETWEEN_CHUNKS), dtype="float32")
                )
            if not parts:
                self.set_status("אין טקסט לשמירה")
                return
            sf.write(path, np.concatenate(parts), sample_rate)
            self.set_status(f"נשמר: {Path(path).name}")
        except Exception as exc:
            self.set_status("שגיאה")
            message = str(exc)
            self.after(0, lambda: messagebox.showerror("שגיאה בשמירה", message))
        finally:
            self._busy(False)


SELFTEST_SENTENCES = [
    "יש לנו 3 ספרים חדשים בכיתה, ואת הראשון נקרא ב-15.10 בשעה 9:30 עם המורה, ב-Zoom.",
    "בפעם ה-2 שניסיתי, קיבלתי 95 בבחינה באנגלית, והמילה הכי קשה הייתה Science.",
    "המחיר הוא 12 שקלים ו-50 אגורות, ואחד מכל 4 תלמידים מעדיף לשמוע את הטקסט ב-Audio.",
]


def selftest(out_dir: str) -> int:
    """No window: read three sentences in each voice into out_dir and write report.json (build.bat runs it)."""
    import json

    import numpy as np
    import soundfile as sf

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    speech = Speech()
    report = {"version": APP_VERSION, "base": str(paths.BASE), "sentences": SELFTEST_SENTENCES, "voices": {}}
    code = 0
    for voice in [v for v in ("basic", "tair") if v in VOICES.values()]:
        entry = {}
        try:
            started = time.time()
            speech.ensure_loaded(voice)
            entry["load_s"] = round(time.time() - started, 1)
            parts, rate, generated = [], 24000, 0.0
            for sentence in SELFTEST_SENTENCES:
                started = time.time()
                samples, rate, _ = speech.synthesize(sentence, voice, "normal")
                generated += time.time() - started
                parts.append(samples.astype("float32"))
                parts.append(np.zeros(int(rate * SILENCE_BETWEEN_CHUNKS), dtype="float32"))
            audio = np.concatenate(parts)
            sf.write(str(out / f"{voice}.wav"), audio, rate)
            seconds = len(audio) / rate
            entry.update(audio_s=round(seconds, 1), gen_s=round(generated, 1),
                         sec_per_audio_sec=round(generated / max(seconds, 0.1), 2),
                         peak=round(float(np.abs(audio).max()), 3), ok=True)
        except Exception as error:  # noqa: BLE001 - the report says what failed
            import traceback

            entry.update(ok=False, error=f"{type(error).__name__}: {error}", trace=traceback.format_exc())
            code = 1
        report["voices"][voice] = entry
    try:
        import sounddevice as sd

        report["audio_devices"] = sum(1 for d in sd.query_devices() if d["max_output_channels"] > 0)
        report["default_output"] = sd.query_devices(kind="output")["name"]
    except Exception as error:  # noqa: BLE001
        report["audio_devices"] = f"error: {error}"
        code = 1
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return code


def _text_from_args(args: list[str]) -> str | None:
    """A .txt file given on the command line (or dropped on HebrewReader.exe) opens with its text."""
    for arg in args:
        path = Path(arg)
        if path.suffix.lower() == ".txt" and path.is_file():
            for encoding in ("utf-8-sig", "cp1255"):
                try:
                    return path.read_text(encoding=encoding)
                except UnicodeDecodeError:
                    continue
    return None


def main() -> None:
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        raise SystemExit(selftest(sys.argv[2]))
    try:
        App(_text_from_args(sys.argv[1:])).mainloop()
    except Exception:
        import traceback

        report = traceback.format_exc()
        (log_dir() / "error.log").write_text(report, encoding="utf-8")
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("שגיאה בהפעלת התוכנה", report)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
