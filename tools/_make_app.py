"""One-time conversion of HebrewSpeaker's app.py into HebrewReader's (9.11.2026). Kept for the record."""
import io
from pathlib import Path

f = Path(__file__).resolve().parent.parent / "app.py"
s = io.open(f, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:80]
    s = s.replace(a, b)


def cut(a_start, b_start, new):
    global s
    i = s.index(a_start)
    j = s.index(b_start, i)
    s = s[:i] + new + s[j:]


rep('''"""
קורא עברית - הקראת טקסט, מקומי לגמרי ובלי אינטרנט.

מקריא עברית ואנגלית, כל שפה במבטא שלה. המנוע עצמו יושב ב-engine.py.
"""''', '''"""
הקורא העברי (HebrewReader) - הקראת טקסט בעברית, מקומית לגמרי ובלי אינטרנט. חינם, מ-ZombieStar Studio.

שני קולות: "קול בסיסי" (StyleTTS2, engine.py, מהיר בכל מחשב) ו"תאיר" (ZipVoice, zip_engine.py, טבעי ואיטי במעבד).
הטקסט לא יוצא מהמחשב: אין כאן שום קריאה לרשת.
"""''')
rep('''from engine import dominant_script
from gemini_engine import KEY_FILE, VOICES, GeminiEngine, MissingKey, split_for_gemini
from hotkey import DEFAULT_LABEL, register_first_available

PACES = {"איטי": "slow", "טבעי": "normal", "מהיר": "fast"}
LOCAL_SPEEDS = {"slow": 0.95, "normal": 1.12, "fast": 1.35}
''', '''import paths
from engine import dominant_script

APP_TITLE = "הקורא העברי"
APP_VERSION = "1.0.0"

VOICE_BASIC = "קול בסיסי (מהיר, כל מחשב)"
VOICE_TAIR = "תאיר (טבעי, מחשב חזק)"
VOICES = {VOICE_BASIC: "basic", VOICE_TAIR: "tair"}
# Measured on the CPU, int8 decoder, 4 threads (README, "the voice תאיר"): the honest number goes in the hint.
TAIR_SECONDS_PER_SECOND = "2.5"
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
''')
cut('class Speech:', 'def _span_index', '''class Speech:
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


def log_dir() -> Path:
    """%LOCALAPPDATA%\\\\HebrewReader: the app folder may be read-only (Program Files, a school share)."""
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "HebrewReader"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return root


''')
rep('''        self.title("קורא עברית")
        self.geometry("820x620")''', '''        self.title(APP_TITLE)
        self.geometry("920x680")''')
rep('''        self._build_style()
        self._build_ui()
        self._bind_shortcuts()
        self._start_hotkey()
        self.protocol''', '''        self._font_size = 16
        self._set_icon()
        self._build_style()
        self._build_ui()
        self._bind_shortcuts()
        self.protocol''')
rep('''    # ---------- עיצוב ----------
''', '''    # ---------- עיצוב ----------

    def _set_icon(self) -> None:
        import sys

        for candidate in (paths.BASE / "icon.ico", Path(getattr(sys, "_MEIPASS", paths.BASE)) / "icon.ico"):
            if candidate.is_file():
                try:
                    self.iconbitmap(default=str(candidate))
                except tk.TclError:
                    pass
                return
''')
rep('''        ttk.Label(head, text="קורא עברית", style="Title.TLabel").pack(anchor="e")
        self.subtitle = ttk.Label(
            head,
            text="העתיקו טקסט מכל מקום, והוא יוקרא מיד.",
            style="Subtitle.TLabel",
        )
        self.subtitle.pack(anchor="e", pady=(2, 0))''', '''        ttk.Button(head, text="אודות", style="Secondary.TButton", command=self.on_about).pack(side="left", anchor="n")
        ttk.Label(head, text=APP_TITLE, style="Title.TLabel").pack(anchor="e")
        self.subtitle = ttk.Label(
            head,
            text="מדביקים טקסט ולוחצים הקרא. הטקסט לא יוצא מהמחשב.",
            style="Subtitle.TLabel",
        )
        self.subtitle.pack(anchor="e", pady=(2, 0))''')
rep('''            font=("Segoe UI", 14),
            undo=True,''', '''            font=("Segoe UI", self._font_size),
            undo=True,''')
rep('''            "1.0", "שלום, כתבו כאן טקסט והוא יוקרא בקול. English works too."''', '''            "1.0",
            "שלום! הדביקו כאן טקסט ולחצו הקרא. אפשר גם מספרים, כמו 3 ספרים ב-15.10, ומילים באנגלית כמו Science.",''')
rep('''        self.pace_var = tk.StringVar(value="טבעי")''', '''        self.pace_var = tk.StringVar(value="רגיל")''')
rep('''        self.voice_var = tk.StringVar(value=next(iter(VOICES)))
        ttk.Combobox(
            picker,
            textvariable=self.voice_var,
            values=list(VOICES),
            state="readonly",
            width=16,
            justify="right",
        ).pack(side="right", padx=(0, 14))''', '''        self.voice_var = tk.StringVar(value=VOICE_BASIC)
        voice_box = ttk.Combobox(
            picker,
            textvariable=self.voice_var,
            values=list(VOICES),
            state="readonly",
            width=24,
            justify="right",
        )
        voice_box.pack(side="right", padx=(0, 14))
        voice_box.bind("<<ComboboxSelected>>", self._on_voice)''')
rep('''        footer = ttk.Frame(root)
        footer.pack(fill="x", pady=(12, 0))
        self.status = ttk.Label(footer, text="מוכן", style="Status.TLabel", anchor="e")
        self.status.pack(side="right")
        self.cost = ttk.Label(footer, text="", style="Status.TLabel", anchor="w")
        self.cost.pack(side="left")''', '''        ttk.Label(picker, text="גודל", style="Field.TLabel").pack(side="right", padx=(14, 6))
        ttk.Button(picker, text="+", width=3, style="Secondary.TButton", command=lambda: self._zoom(1)).pack(side="right")
        ttk.Button(picker, text="-", width=3, style="Secondary.TButton", command=lambda: self._zoom(-1)).pack(
            side="right", padx=(0, 4)
        )

        self.hint = ttk.Label(root, text="", style="Status.TLabel", anchor="e", justify="right", wraplength=860)
        self.hint.pack(fill="x", pady=(10, 0))

        footer = ttk.Frame(root)
        footer.pack(fill="x", pady=(6, 0))
        self.status = ttk.Label(footer, text="מוכן", style="Status.TLabel", anchor="e")
        self.status.pack(side="right")''')
cut('    def _start_hotkey(self) -> None:', '    def read_clipboard(self) -> None:', '''    def _on_voice(self, _event=None) -> None:
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

''')
rep('''    def _on_close(self) -> None:
        self._stop_flag.set()
        try:
            self._hotkey.stop()
        except Exception:
            pass
        self.destroy()''', '''    def _on_close(self) -> None:
        self._stop_flag.set()
        self.destroy()''')
cut('    def _prepare(self) -> tuple[str, str]:', '    def _play_worker(', '''    def _prepare(self) -> tuple[str, str]:
        voice, pace = VOICES[self.voice_var.get()], PACES[self.pace_var.get()]
        self.engine.ensure_loaded(voice, self.set_status)
        return voice, pace

''')
rep('''                        samples, sr, spans, _ = self.engine.synthesize(chunk, voice, pace)''', '''                        samples, sr, spans = self.engine.synthesize(chunk, voice, pace)''')
rep('''                    self.after(0, self._show_cost)
                    if samples is None:
                        continue
                    audio_queue.put''', '''                    if samples is None:
                        continue
                    audio_queue.put''')
rep('''            while not self._stop_flag.is_set():
                item = audio_queue.get()''', '''            if voice == "tair":
                self.set_status("תאיר מכין את המשפט הראשון...")
            while not self._stop_flag.is_set():
                item = audio_queue.get()''')
rep('''                samples, sample_rate, _, _ = self.engine.synthesize(chunk, voice, pace)
                self.after(0, self._show_cost)''', '''                samples, sample_rate, _ = self.engine.synthesize(chunk, voice, pace)''')
rep('''        (Path(__file__).parent / "error.log").write_text(report, encoding="utf-8")''', '''        (log_dir() / "error.log").write_text(report, encoding="utf-8")''')
rep('''def main() -> None:
    try:''', '''SELFTEST_SENTENCES = [
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
    for voice in ("basic", "tair"):
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
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return code


def main() -> None:
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        raise SystemExit(selftest(sys.argv[2]))
    try:''')
io.open(f, "w", encoding="utf-8", newline="").write(s)
print("app.py converted")
