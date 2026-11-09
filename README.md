# הקורא העברי (HebrewReader)

תוכנה חינמית ל-Windows שמקריאה טקסט בעברית, בשביל תלמידים שקשה להם לקרוא. היא רצה כולה על המחשב ולא מתחברת לרשת, כך שהטקסט לא יוצא מהמחשב.
ZombieStar Studio, 9.11.2026. קוד פתוח תחת GPL-3.0-or-later (`LICENSE`).

נבנתה מתוך `C:\Tair\Tools\HebrewSpeaker`, הכלי שההאב משתמש בו. HebrewSpeaker נשאר כמו שהוא; זה עותק נפרד.

## מה יש בה

| | |
|---|---|
| `app.py` | החלון (tkinter): הדבקה, הקראה עם קו מתחת למילה, עצירה והמשך, שמירת WAV, גודל טקסט, אודות. `--selftest <תיקייה>` מקריא שלושה משפטים בכל קול ושומר את `report.json` |
| `engine.py` | הקול הבסיסי: Piper "noa" (עברית) ו-ljspeech (משפט אנגלי שלם), ReNikud לעברית, eSpeak לאנגלית. הפיצול לפי שפה והתפרים לקוחים מ-HebrewSpeaker |
| `hebrew_text.py`, `lexicon.txt` | שכבת הקריאה: מספרים לפי המין של שם העצם, תאריכים, שעות, ראשי תיבות, מילון וניקוד. הקוד זהה לזה של HebrewSpeaker |
| `zip_engine.py`, `pace_stretch.py`, `vendor/zipvoice_onnx` | הקול "תאיר" (ZipVoice, int8, רק על המעבד). **פרטי, לא לפרסום**, ראו בהמשך |
| `vendor/zipvoice_onnx/dsp.py` | שש פונקציות של librosa שנכתבו מחדש ב-numpy, כדי ש-numba, llvmlite ו-sklearn לא ייכנסו לחבילה. `tests/test_dsp.py` משווה אותן ל-librosa עצמה |
| `paths.py` | מאיפה נטענים הקבצים: ליד ה-exe בבילד, וליד הקוד בהרצה מהמקור |
| `tools/build.py`, `HebrewReader.spec`, `build.bat` | הבנייה, ראו בהמשך |
| `tools/get_models.py` | מוריד את המודלים של הקול הבסיסי מהדפים של היוצרים |
| `tools/bench.py` | מדידה: כמה שניות הכנה לכל שנייה של דיבור, ודיוק מילים לפי Whisper (שירות ה-ASR המקומי בפורט 8768) |

## הקולות, ולמה דווקא אלה

| קול בבורר | מנוע | רישיון | מהירות (4 ליבות) | Whisper, 5 משפטים | NISQA-TTS טבעיות |
|---|---|---|---|---|---|
| קול בסיסי (מהיר, כל מחשב) | Piper noa, `models/piper` (77MB) | CC BY 4.0 | 0.3 שניות לשנייה (פי 3.5 מהיר מזמן אמת) | 100% | 4.53 |
| תאיר (טבעי, מחשב חזק) | ZipVoice int8 + `voices/tair.wav` | **לא ידוע**, ראו בהמשך | 2 עד 2.5 שניות לשנייה | 96% | 3.94 |

מדידה מ-9.11.2026, רק על המעבד (`HR_THREADS=4`, דומה למחשב נייד רגיל), עם `tools/bench.py` ועם `C:\Tair\Tools\VoiceLab\harness\measure.py`.

**הקול הבסיסי הוחלף.** ב-HebrewSpeaker הוא היה StyleTTS2 (`libritts_hebrew.onnx` ו-`libritts_english.onnx`). את המקור והרישיון של שני המודלים האלה אי אפשר לבדוק: הם ירדו מה-releases של `thewh1teagle/style-onnx`, והמאגר נמחק. גם המשפחה הקרובה להם (phonikud-tts, SASPEECH, ILSpeech) מוגבלת לשימוש לא מסחרי. Piper noa יצא חוקי, מהיר וקטן יותר, ובמדידה גם טבעי יותר.

**"תאיר" הוא ZipVoice, והגרסה הציבורית לא כוללת אותו.** קובץ ה-checkpoint העברי ירד מ-`huggingface.co/thewh1teagle/zipvoice-heb` ומה-releases של `thewh1teagle/zipvoice-onnx`. שני המקורות נמחקו, ולא ידוע על מה הוא אומן. גם הקוד המוטמע ב-`vendor/zipvoice_onnx` הגיע בלי קובץ רישיון. האפליקציה מציגה את "תאיר" בבורר רק כשהחבילה שלו נמצאת בתיקייה (`models/zipvoice` ו-`voices/tair.*`). הפירוט ב-`C:\Tair\Daily\zombiestar\business\legal\hebrew-reader-licenses.md`.

הגדרות "תאיר": מפענח int8 ו-16 צעדים. int8 עם 16 צעדים נתן NISQA 4.45 מול 4.91 של המודל המלא, ובגודל של רבע: 130MB במקום 495MB. עם 8 צעדים הציון ירד ל-4.09, ולכן לא נבחר. המודל המלא איטי יותר: 3.6 שניות לכל שנייה של דיבור.

## בנייה

```
uv sync
.venv\Scripts\python.exe tools\get_models.py
build.bat public    ->  release\HebrewReader-1.0.0-win64.zip                  ההורדה לתלמידים
build.bat full      ->  release\HebrewReader-1.0.0-win64-with-tair-PRIVATE.zip  עם "תאיר", רק למחשב של תאיר
```

הבנייה היא PyInstaller onedir. התיקיות `models`, `voices`, `lexicon.txt`, `CREDITS.txt`, `licenses` ו-`SOURCE.txt` יושבות ליד `HebrewReader.exe`, ולא בתוך `_internal`. `tools/build.py` מוחק מהחבילה את כל השפות של eSpeak חוץ מאנגלית, את כל ה-locales של babel חוץ מ-en ו-he, ואת גרסאות PortAudio של 32 ביט, ARM ו-ASIO. הבילד הציבורי לא כולל את scipy (68MB): הדגימה מחדש מ-22.05 ל-24 קילוהרץ נעשית ב-numpy, ב-`engine.resample`, עם יחס אות לרעש של 93 עד 105 דציבל.

גודל ב-9.11.2026: הציבורי 132.5MB ב-zip ו-210MB אחרי פריסה. הפרטי 312MB ב-zip ו-471MB אחרי פריסה.

## בדיקה כמו תלמיד

פורסים את ה-zip לתיקייה חדשה ומריצים `HebrewReader.exe --selftest <תיקייה>` מחוץ ל-venv, עם PATH ריק. הבדיקה כותבת `basic.wav`, `tair.wav` ו-`report.json`. ב-9.11 עברו שני הבילדים, ו-Whisper שמע נכון את "שלושה ספרים", "ב-15 באוקטובר", "בפעם השנייה", "Science" ו"אודיו". בזמן שהחלון היה פתוח, לתהליך לא היה אף חיבור TCP או UDP (`Get-NetTCPConnection`).

הבדיקות: `.venv\Scripts\python.exe -X utf8 -m unittest tests.test_hebrew_text`. את `tests.test_dsp` מריצים מה-venv של HebrewSpeaker, כי רק בו מותקנת librosa.
