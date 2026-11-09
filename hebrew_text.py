# -*- coding: utf-8 -*-
"""The reading layer: Hebrew text the way it should be said, before the G2P model sees it.

ReNikud (the G2P in engine.py) reads plain Hebrew words well and nothing else. Measured 15.10.2026: it ignores
nikud (a pointed word came back as garbage), it reads digits as nothing, every number the old expander gave it was
feminine ("שלוש ימים", "אחת שקל"), dates came out feminine too, and loanwords and abbreviations were guessed letter
by letter ("דוח" -> dχo, "פיקסל" -> fiksel, "סה"כ" -> shak). Everything that is not a plain Hebrew word is therefore
settled here first, and the model only gets what it is good at:

* numbers in the gender of the noun they count ("3 ימים" -> שלושה ימים, "3 שעות" -> שלוש שעות, "1 שעה" -> שעה
  אחת, "2 שקלים" -> שני שקלים, "3 הימים" -> שלושת הימים), labels after a noun in the feminine Israelis use
  ("שלב 3" -> שלב שלוש, but "שלב 1" -> שלב אחד), ordinals ("בפעם ה-3" -> בפעם השלישית), dates in the masculine
  ("15.10.2026" -> חמישה עשר באוקטובר אלפיים עשרים ושש), times, percents, money, ranges, decimals ("3.5 שעות" ->
  שלוש וחצי שעות), phone numbers digit by digit, and a prefix glued on ("ב-15" -> בחמישה עשר, "ו-2" -> ושתי);
* abbreviations with gershayim or a geresh and words the model mispronounces, from lexicon.txt beside this file:
  a replacement in IPA (/.../), in Hebrew with nikud, or in plain Hebrew (ארה"ב -> ארצות הברית);
* any word written with nikud in the text itself is read exactly as pointed, through phonikud's rules, so nikud is
  the way to force a pronunciation once without touching the lexicon.

IPA islands pass through ReNikud untouched (it copies every non-Hebrew character and reads the Hebrew around them
as before - measured), so prepare() returns a mix of Hebrew words for the model and IPA for words already settled.
The word count of the text is not kept (a number becomes several words); the engines time their highlight on the
original text, so that does not matter.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import paths

BASE = paths.BASE
LEXICON_FILE = paths.LEXICON

HEBREW = "א-ת"
_HEBREW_WORD = re.compile(rf"^[{HEBREW}]+$")
_POINTS = re.compile(r"[֑-ֽֿ-ׇ]")  # nikud and accents; the maqaf (05be) is not a point
_EDGE = ".,!?;:…\"'()[]{}<>«»-–—*_/\\|"

# ---------- number words ----------

ONES = {
    "f": ["", "אחת", "שתיים", "שלוש", "ארבע", "חמש", "שש", "שבע", "שמונה", "תשע"],
    "m": ["", "אחד", "שניים", "שלושה", "ארבעה", "חמישה", "שישה", "שבעה", "שמונה", "תשעה"],
}
TEENS = {
    "f": ["עשר", "אחת עשרה", "שתים עשרה", "שלוש עשרה", "ארבע עשרה", "חמש עשרה", "שש עשרה", "שבע עשרה",
          "שמונה עשרה", "תשע עשרה"],
    "m": ["עשרה", "אחד עשר", "שנים עשר", "שלושה עשר", "ארבעה עשר", "חמישה עשר", "שישה עשר", "שבעה עשר",
          "שמונה עשר", "תשעה עשר"],
}
TENS = ["", "", "עשרים", "שלושים", "ארבעים", "חמישים", "שישים", "שבעים", "שמונים", "תשעים"]
HUNDREDS = ["", "מאה", "מאתיים", "שלוש מאות", "ארבע מאות", "חמש מאות", "שש מאות", "שבע מאות", "שמונה מאות",
            "תשע מאות"]
THOUSANDS = ["", "אלף", "אלפיים", "שלושת אלפים", "ארבעת אלפים", "חמשת אלפים", "ששת אלפים", "שבעת אלפים",
             "שמונת אלפים", "תשעת אלפים", "עשרת אלפים"]
# the form before a noun: "שני ימים", "שתי שעות", "שלושת הימים" (3-10 only before a definite noun)
CONSTRUCT = {
    "f": ["", "", "שתי", "שלוש", "ארבע", "חמש", "שש", "שבע", "שמונה", "תשע", "עשר"],
    "m": ["", "", "שני", "שלושת", "ארבעת", "חמשת", "ששת", "שבעת", "שמונת", "תשעת", "עשרת"],
}
ORDINALS = {
    "f": ["", "ראשונה", "שנייה", "שלישית", "רביעית", "חמישית", "שישית", "שביעית", "שמינית", "תשיעית", "עשירית"],
    "m": ["", "ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שביעי", "שמיני", "תשיעי", "עשירי"],
}
DIGITS = ["אפס", "אחת", "שתיים", "שלוש", "ארבע", "חמש", "שש", "שבע", "שמונה", "תשע"]
MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר",
          "דצמבר"]

# ---------- the gender of nouns ----------

# Nouns that come after a number, singular and plural. The plural suffix (ים / ות) decides for a word that is not
# here, so the table carries the exceptions and the everyday words the hub reads: time, money, the game, the code.
GENDER = {}
for _word in ("יום ימים שבוע שבועות חודש חודשים אחוז אחוזים שקל שקלים דולר דולרים אירו סנט סנטים מיליון מיליארד "
              "אלף אלפים מטר מטרים קילומטר קילומטרים סנטימטר מילימטר קילו קילוגרם גרם גרמים ליטר ליטרים מגהבייט "
              "ג'יגהבייט קילובייט טרהבייט בייט בייטים פיקסל פיקסלים פריים פריימים קובץ קבצים עמוד עמודים סרטון "
              "סרטונים משחק משחקים שחקן שחקנים משתמש משתמשים איש אנשים ילד ילדים תלמיד תלמידים שלב שלבים פרק "
              "פרקים שיעור שיעורים כרטיס כרטיסים לקוח לקוחות דבר דברים באג באגים קומיט קומיטים צעד צעדים חלק "
              "חלקים סיבוב סיבובים ניסיון ניסיונות נסיון נסיונות מקום מקומות ספר ספרים בית בתים חדר חדרים טלפון "
              "טלפונים מחשב מחשבים דוח דוחות קליק קליקים לייק לייקים עוקב עוקבים מנוי מנויים עותק עותקים טוקן "
              "טוקנים לוג לוגים אייקון אייקונים ספרייט ספרייטים שרת שרתים מסך מסכים כפתור כפתורים מכתב מכתבים "
              "רגע רגעים שיר שירים קול קולות לילה לילות שולחן שולחנות קיר קירות חלון חלונות רחוב רחובות שם שמות "
              "אב אבות מקצוע מקצועות לוח לוחות ארון ארונות חלום חלומות סוד סודות רעיון רעיונות מוסד מוסדות "
              "עיקרון עקרונות מקור מקורות כוח כוחות דור דורות וילון וילונות כיסא כיסאות פרי פירות נר נרות עור "
              "עורות מזל מזלות שירות שירותים צוות צוותים שבוע מכשיר מכשירים רכב רכבים אוטובוס אוטובוסים מטוס "
              "מטוסים מפגש מפגשים אירוע אירועים פרויקט פרויקטים מודל מודלים סקיל סקילים הוק הוקים ג'וב ג'ובים "
              "אחוז מועמד מועמדים חבר חברים ראיון ראיונות גיל ציון ציונים זמן זמנים חלק יתרון יתרונות חיסרון "
              "חסרונות מבחן מבחנים מיליונים מיליארדים").split():
    GENDER[_word] = "m"
for _word in ("שעה שעות דקה דקות שנייה שניות שניה שנה שנים פעם פעמים נקודה נקודות שורה שורות מילה מילים הודעה "
              "הודעות תמונה תמונות ילדה ילדות רמה רמות גרסה גרסאות עיר ערים מכירה מכירות הורדה הורדות משימה משימות "
              "בעיה בעיות שאלה שאלות תשובה תשובות אגורה אגורות מעלה מעלות יחידה יחידות צפייה צפיות צפיה "
              "אישה נשים אבן אבנים דרך דרכים עין עיניים רגל רגליים יד ידיים שן שיניים ביצה ביצים ציפור ציפורים "
              "אצבע אצבעות כוס כוסות דלת דלתות ארץ ארצות כיכר כיכרות אות אותיות מילישנייה מילישניות מילי-שניות "
              "משבצת משבצות רשימה רשימות קבוצה קבוצות פגישה פגישות שיחה שיחות תוכנית תוכניות תכנית תכניות קומה "
              "קומות כיתה כיתות מחלקה מחלקות עונה עונות דקות שקית שקיות חבילה חבילות מנה מנות עוגה עוגות "
              "חתיכה חתיכות אפשרות אפשרויות תכונה תכונות שגיאה שגיאות אזהרה אזהרות בקשה בקשות הצעה הצעות עסקה "
              "עסקאות הזמנה הזמנות מכונה מכונות רכבת רכבות ספינה ספינות חללית חלליות טיסה טיסות נסיעה נסיעות "
              "דוגמה דוגמאות הרצה הרצות גישה פנייה פניות הקלטה הקלטות סצנה סצנות אנימציה אנימציות תחנה תחנות "
              "תגובה תגובות כתבה כתבות עבודה עבודות מכה מכות דקה").split():
    GENDER[_word] = "f"

# A plural that must become singular after "1": "1 שקלים" is said "שקל אחד". Words not here lose their ים, or
# trade their ות for a ה, which is right often enough for a text nobody should have written that way.
SINGULAR = {
    "שקלים": "שקל", "ימים": "יום", "שעות": "שעה", "דקות": "דקה", "שניות": "שנייה", "אחוזים": "אחוז",
    "פעמים": "פעם", "אנשים": "איש", "ילדים": "ילד", "שבועות": "שבוע", "חודשים": "חודש", "שנים": "שנה",
    "שחקנים": "שחקן", "נקודות": "נקודה", "משתמשים": "משתמש", "קבצים": "קובץ", "דולרים": "דולר", "מטרים": "מטר",
    "קילומטרים": "קילומטר", "עמודים": "עמוד", "מילים": "מילה", "דברים": "דבר", "בעיות": "בעיה", "לקוחות": "לקוח",
    "פריימים": "פריים", "פיקסלים": "פיקסל", "גרסאות": "גרסה", "ערים": "עיר", "מקומות": "מקום", "בתים": "בית",
    "דוחות": "דוח", "מעלות": "מעלה", "ליטרים": "ליטר", "גרמים": "גרם", "נשים": "אישה", "אבנים": "אבן",
    "דרכים": "דרך", "ארצות": "ארץ", "אותיות": "אות", "דוגמאות": "דוגמה", "עסקאות": "עסקה", "שמות": "שם",
    "לילות": "לילה", "קולות": "קול", "רעיונות": "רעיון", "ניסיונות": "ניסיון", "אפשרויות": "אפשרות",
    "צפיות": "צפייה", "מילישניות": "מילישנייה", "ציפורים": "ציפור", "כיסאות": "כיסא", "ארונות": "ארון",
    "פירות": "פרי", "מכשירים": "מכשיר", "אירועים": "אירוע", "פרויקטים": "פרויקט",
}

# Words that stand before a number without naming what it counts: after these the number is not a label.
NOT_A_LABEL = set("עד מ ב ל של על עם או גם רק כבר עוד יש אין לפני אחרי בערך כמעט מעל מתחת בין פי כ ועוד בסך סך "
                  "הכל הכול בעוד תוך במשך כל היו הם הן זה זאת זו את לא כן מספר היה הייתה הייתי היינו יהיה תהיה "
                  "יהיו עלה עלתה ירד ירדה עולה יורד עולים יורדים קיבל קיבלה קיבלתי שילם שילמה שילמתי מגיע מגיעה "
                  "מגיעים להוסיף לקנות לקבל לשלם לתת לעשות עשיתי עשה עשתה עושה עושים נשארו נשאר נשארה "
                  "בדיוק לפחות לכל היותר עוד בסביבות סביב לאורך ועד מבין כולל ללא בלי פלוס מינוס שווה "
                  "מתוך לגבי אפילו בדרך אולי כנראה בטח ממש".split())

PREFIX_IPA = {
    "ו": "ve", "ה": "ha", "ב": "be", "ל": "le", "מ": "me", "ש": "ʃe", "כ": "ke",
    "וה": "veha", "וב": "uve", "ול": "ule", "ומ": "ume", "וש": "veʃe", "וכ": "uχe",
    "שה": "ʃeha", "כש": "keʃe", "מה": "meha", "שב": "ʃebe", "שמ": "ʃeme", "של": "ʃele",
    "ושה": "veʃeha", "וכש": "ukʃe", "ומה": "umeha",
}
_PREFIX_LETTERS = "ובכלמשה"


def _join(parts: list[str]) -> str:
    """Hebrew puts its "ו" before the last group: מאה עשרים ושלוש, אלף ומאתיים, אלפיים עשרים ושש."""
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return " ".join(parts[:-1]) + " ו" + parts[-1]


def _under_thousand(n: int, g: str) -> list[str]:
    parts = [HUNDREDS[n // 100]]
    rest = n % 100
    if rest < 10:
        parts.append(ONES[g][rest])
    elif rest < 20:
        parts.append(TEENS[g][rest - 10])
    else:
        parts += [TENS[rest // 10], ONES[g][rest % 10]]
    return parts


def cardinal(n: int, gender: str = "f") -> str:
    """A whole number in words. Thousands, millions and the tens are the same in both genders; the units follow
    the noun: "עשרים ושלושה ימים", "עשרים ושלוש שעות"."""
    if n < 0:
        return "מינוס " + cardinal(-n, gender)
    if n == 0:
        return "אפס"
    if n >= 10 ** 12:
        return " ".join(DIGITS[int(d)] for d in str(n))
    parts: list[str] = []
    billions, n = divmod(n, 10 ** 9)
    if billions:
        parts.append({1: "מיליארד", 2: "שני מיליארד"}.get(billions) or cardinal(billions, "m") + " מיליארד")
    millions, n = divmod(n, 10 ** 6)
    if millions:
        parts.append({1: "מיליון", 2: "שני מיליון"}.get(millions) or cardinal(millions, "m") + " מיליון")
    thousands, n = divmod(n, 1000)
    if thousands:
        parts.append(THOUSANDS[thousands] if thousands <= 10 else cardinal(thousands, "m") + " אלף")
    parts += _under_thousand(n, gender)
    return _join(parts)


def digits(text: str) -> str:
    """A number read digit by digit: phone numbers, identity numbers, codes."""
    return " ".join(DIGITS[int(c)] if c.isdigit() else c for c in text if c.isdigit() or c in "-")


def ordinal(n: int, gender: str) -> str:
    """"ה-3" after a noun: השלישי / השלישית; past ten Hebrew says the cardinal with a ה."""
    if 1 <= n <= 10:
        return "ה" + ORDINALS[gender][n]
    return "ה" + cardinal(n, gender)


def _strip_definite(word: str) -> str:
    return word[1:] if word.startswith("ה") and len(word) > 2 else word


_NOUN_PREFIXES = sorted(PREFIX_IPA, key=len, reverse=True)


def noun_gender(word: str, singular: bool = False) -> str | None:
    """The gender of a noun, or None when the word does not look like a noun at all (not Hebrew, or a plural
    suffix is missing when a plural is expected). A prefix (בפעם, לשעה, מהיום) is looked behind."""
    word = _POINTS.sub("", word)
    if not word:
        return None
    if word in GENDER:
        return GENDER[word]
    for prefix in _NOUN_PREFIXES:
        if word.startswith(prefix) and word[len(prefix):] in GENDER:
            return GENDER[word[len(prefix):]]
    if not _HEBREW_WORD.match(word.replace("'", "")):
        return None
    stem = _strip_definite(word)
    if singular:
        return "f" if stem.endswith(("ה", "ת")) else "m"
    if stem.endswith("ות") and len(stem) > 3:
        return "f"
    if stem.endswith("ים") and len(stem) > 3:
        return "m"
    return None


def singular_of(word: str) -> str:
    definite = word.startswith("ה") and len(word) > 3 and (word[1:] in SINGULAR or word[1:] in GENDER)
    stem = word[1:] if definite else word
    if stem in SINGULAR:
        one = SINGULAR[stem]
    elif stem.endswith("ות") and len(stem) > 4 and GENDER.get(stem, "f") == "f":
        one = stem[:-2] + "ה"
    elif stem.endswith("ים") and len(stem) > 4 and GENDER.get(stem, "m") == "m":
        one = stem[:-2]
    else:
        one = stem
    return ("ה" + one) if definite else one


def _is_month(word: str) -> bool:
    core = word
    if core[:1] in "בלמ" and core[1:] in MONTHS:
        return True
    return core in MONTHS


# ---------- the passes over the text ----------

_THOUSANDS = re.compile(r"(\d),(?=\d{3}(?!\d))")
_PHONE = re.compile(r"(?<![\d\w])(0\d{1,2})-?(\d{7})(?![\d\w])")
_LONG_DIGITS = re.compile(r"(?<![\d.,])\d{8,}(?![\d.,])")
_FULL_DATE = re.compile(r"(?<![\d.])(\d{1,2})[./](\d{1,2})[./](\d{4})(?![\d.])")
_ISO_DATE = re.compile(r"(?<![\d.])(\d{4})-(\d{2})-(\d{2})(?![\d.])")
_SHORT_DATE = re.compile(r"(?<![\d.])(1[3-9]|2\d|3[01])\.(\d{1,2})(?![\d.])")
_RANGE = re.compile(r"(?<![\d.])(\d{1,4})[-–](\d{1,4})(?![\d.])")
_NEGATIVE = re.compile(r"(?:(?<=\s)|^)-(?=\d)")
_TIME = re.compile(r"(?<![\d:])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])")
_PERCENT = re.compile(r"(\d)\s?%")
_MONEY_BEFORE = re.compile(r"([$€₪])\s?(\d+(?:[.,]\d+)*)")
_MONEY_AFTER = re.compile(r"(\d+(?:[.,]\d+)*)\s?([$€₪])")
_CURRENCY = {"$": "דולר", "€": "אירו", "₪": "שקלים"}
_BY = re.compile(r"(?<![\d.])(\d+)\s?[x×]\s?(\d+)(?![\d.])")
_DEGREES = re.compile(r"(\d)\s?°")
_HASH = re.compile(r"#(?=\d)")
_PLUS = re.compile(r"(?<=\d)\+(?![\d\w])")
_INNER_HYPHEN = re.compile(rf"(?<=[{HEBREW}])[-–](?=[{HEBREW}])")
# a prefix letter left alone at the end of a Hebrew run ("ב-" before an English word the other model reads)
_DANGLING_PREFIX = re.compile(rf"(?<![{HEBREW}])([{_PREFIX_LETTERS}])[-–]\s*$")
_NUMBER = re.compile(rf"^(?P<pre>[{_PREFIX_LETTERS}]{{0,3}})-?(?P<num>\d+(?:\.\d+)*)$")


def _month_name(number: str) -> str | None:
    index = int(number)
    return MONTHS[index - 1] if 1 <= index <= 12 else None


def _full_date(match: re.Match) -> str:
    day, month, year = int(match.group(1)), _month_name(match.group(2)), match.group(3)
    if month is None or not 1 <= day <= 31:
        return match.group(0)
    return f"{day} ב{month} {year}"


def _iso_date(match: re.Match) -> str:
    year, month, day = match.group(1), _month_name(match.group(2)), int(match.group(3))
    if month is None or not 1 <= day <= 31:
        return match.group(0)
    return f"{day} ב{month} {year}"


def _short_date(match: re.Match) -> str:
    month = _month_name(match.group(2))
    return f"{int(match.group(1))} ב{month}" if month else match.group(0)


def _time(match: re.Match) -> str:
    hour, minutes = int(match.group(1)), int(match.group(2))
    return f"{hour}" if minutes == 0 else f"{hour} ו-{minutes}"


def _phone(match: re.Match) -> str:
    return digits(match.group(1)) + ", " + digits(match.group(2))


def normalize_symbols(text: str) -> str:
    """Everything a regex can settle without knowing the neighbours: dates, times, money, ranges, phones."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("״", '"').replace("׳", "'").replace("־", "-").replace("’", "'")
    text = _PHONE.sub(_phone, text)
    text = _THOUSANDS.sub(r"\1", text)
    text = _LONG_DIGITS.sub(lambda m: digits(m.group(0)), text)
    text = _ISO_DATE.sub(_iso_date, text)
    text = _FULL_DATE.sub(_full_date, text)
    text = _SHORT_DATE.sub(_short_date, text)
    text = _TIME.sub(_time, text)
    text = _RANGE.sub(r"\1 עד \2", text)
    text = _NEGATIVE.sub("מינוס ", text)
    text = _PERCENT.sub(r"\1 אחוז", text)
    text = _MONEY_BEFORE.sub(lambda m: f"{m.group(2)} {_CURRENCY[m.group(1)]}", text)
    text = _MONEY_AFTER.sub(lambda m: f"{m.group(1)} {_CURRENCY[m.group(2)]}", text)
    text = _DEGREES.sub(r"\1 מעלות", text)
    text = _BY.sub(r"\1 על \2", text)
    text = _HASH.sub("מספר ", text)
    text = _PLUS.sub(" פלוס", text)
    text = _INNER_HYPHEN.sub(" ", text)
    return _DANGLING_PREFIX.sub(r"\1", text)


def _split_token(token: str) -> tuple[str, str, str]:
    """Leading punctuation, the word, trailing punctuation. A geresh right after a Hebrew letter belongs to the
    word (וכו', מס'), and gershayim inside a word are never edges (ארה"ב)."""
    lead = 0
    while lead < len(token) and token[lead] in _EDGE:
        lead += 1
    trail = len(token)
    while trail > lead and token[trail - 1] in _EDGE:
        trail -= 1
    if trail < len(token) and token[trail] == "'" and trail > lead and re.match(rf"[{HEBREW}]", token[trail - 1]):
        trail += 1
    return token[:lead], token[lead:trail], token[trail:]


class _Words:
    """The tokens of a text, with the number pass that needs to look at neighbours."""

    def __init__(self, text: str) -> None:
        self.parts = [_split_token(t) for t in text.split()]
        self.out: list[str] = []
        self.skip = 0

    def core(self, index: int) -> str:
        if 0 <= index < len(self.parts):
            return self.parts[index][1]
        return ""

    def gender_after(self, index: int, singular: bool) -> str | None:
        """The gender the noun after the number asks for. "3 עד 5 ימים" and "3 או 4 ימים" look past the range;
        punctuation right after the number ("שלב 1, שלב 3") ends the phrase, so the next word is not its noun."""
        if self.parts[index][2].strip("\"')]}»"):
            return None
        word = self.core(index + 1)
        if word in ("עד", "או") and _NUMBER.match(self.core(index + 2)):
            return self.gender_after(index + 2, singular)
        if word in ("אחוז", "אחוזים", "מיליון", "מיליארד", "אלף", "אלפים") or _is_month(word):
            return "m"
        return noun_gender(word, singular)

    @staticmethod
    def _known_noun(word: str) -> bool:
        """A word the gender table knows, or a plural: a noun for sure, not just any Hebrew word."""
        word = _POINTS.sub("", word)
        if word in GENDER or _strip_definite(word) in GENDER:
            return True
        return any(word.startswith(p) and word[len(p):] in GENDER for p in _NOUN_PREFIXES) or \
            noun_gender(word, singular=False) is not None

    def is_label(self, index: int) -> bool:
        """"שלב 3", "גרסה 218", "עמוד 12": a number after the noun it names, said in the feminine."""
        prev = self.core(index - 1)
        if index == 0 or not prev or not _HEBREW_WORD.match(prev.replace("'", "")):
            return False
        if self.parts[index - 1][2]:  # punctuation between them: not the same phrase
            return False
        return prev not in NOT_A_LABEL and _strip_definite(prev) not in NOT_A_LABEL

    def number(self, index: int, lead: str, match: re.Match, trail: str) -> str:
        pre, raw = match.group("pre"), match.group("num")
        if raw.count(".") > 1 or (raw.startswith("0") and len(raw) > 1 and "." not in raw):
            # a version (1.2.3) or a code with a leading zero: digit by digit
            words = " ".join(digits(p) if p.isdigit() else "נקודה" for p in re.split(r"(\.)", raw))
            return lead + self._glue(pre, words) + trail
        if "." in raw:
            return lead + self._glue(pre, self._decimal(index, raw)) + trail
        n = int(raw)
        definite = pre.endswith("ה")
        rest = pre[:-1] if definite else pre
        next_word = self.core(index + 1)

        if definite and not _is_month(next_word):
            if self.is_label(index):
                gender = noun_gender(self.core(index - 1), singular=True) or "f"
                return lead + rest + ordinal(n, gender) + trail
            gender = self.gender_after(index, singular=n == 1) or "f"
            return lead + rest + "ה" + cardinal(n, gender) + trail

        prefix = rest if definite else pre
        if definite:
            prefix = rest + "ה"
        gender = self.gender_after(index, singular=n == 1)
        # a number with a prefix ("שעה ו-1 פיצ'ר", "ימים ב-3 שקלים") opens its own phrase: never a label of the word before
        label = self.is_label(index) and not pre
        if n == 1 and gender is not None and not _is_month(next_word) and not self._known_noun(next_word) and label:
            # "שלב 1 קל": the word after is not a noun the table knows, and the word before names the number
            gender = None
        if gender is not None:
            if 2 <= n <= 10 and next_word == "אלף":
                # "3 אלף" is said "שלושת אלפים"
                self.skip = 1
                return lead + self._glue(prefix, THOUSANDS[n]) + self.parts[index + 1][2]
            if n == 1 and _HEBREW_WORD.match(_POINTS.sub("", next_word).replace("'", "")) and not _is_month(next_word):
                # "1 שעה" is said "שעה אחת": the noun moves forward and takes the prefix
                noun = singular_of(next_word)
                self.skip = 1
                noun_lead, _core, noun_trail = self.parts[index + 1]
                return lead + noun_lead + prefix + noun + " " + ONES[gender][1] + noun_trail
            if n == 2:
                return lead + self._glue(prefix, CONSTRUCT[gender][2]) + trail
            if 3 <= n <= 10 and next_word.startswith("ה") and len(next_word) > 3:
                return lead + self._glue(prefix, CONSTRUCT[gender][n]) + trail
            return lead + self._glue(prefix, cardinal(n, gender)) + trail
        if label:
            gender = (noun_gender(self.core(index - 1), singular=True) or "m") if n == 1 else "f"
            return lead + self._glue(prefix, cardinal(n, gender)) + trail
        return lead + self._glue(prefix, cardinal(n, "f")) + trail

    def _decimal(self, index: int, raw: str) -> str:
        whole, fraction = raw.split(".")
        gender = self.gender_after(index, singular=False) or "f"
        if fraction == "5":
            return "חצי" if int(whole) == 0 else cardinal(int(whole), gender) + " וחצי"
        return cardinal(int(whole), gender) + " נקודה " + " ".join(DIGITS[int(c)] for c in fraction)

    @staticmethod
    def _glue(prefix: str, words: str) -> str:
        return prefix + words if prefix else words

    def run(self) -> str:
        for index, (lead, core, trail) in enumerate(self.parts):
            if self.skip:
                self.skip -= 1
                continue
            match = _NUMBER.match(core) if core and core[-1].isdigit() else None
            if match and match.group("num"):
                self.out.append(self.number(index, lead, match, trail))
            else:
                self.out.append(lead + core + trail)
        return " ".join(self.out)


def speak_numbers(text: str) -> str:
    """Every number in words, in the gender of what it counts. Expects normalize_symbols() to have run."""
    return _Words(text).run()


# ---------- the lexicon and nikud ----------

class Lexicon:
    """lexicon.txt: one entry per line, `word = replacement`, `#` starts a comment. The replacement is IPA between
    slashes, Hebrew with nikud (read by phonikud's rules), or plain Hebrew. Reloaded whenever the file changes."""

    def __init__(self, path: Path = LEXICON_FILE) -> None:
        self.path = path
        self._stamp = None
        self._entries: dict[str, tuple[str, str]] = {}

    def entries(self) -> dict[str, tuple[str, str]]:
        try:
            stamp = self.path.stat().st_mtime_ns
        except OSError:
            stamp = None
        if stamp != self._stamp:
            self._stamp = stamp
            self._entries = self._load() if stamp is not None else {}
        return self._entries

    def _load(self) -> dict[str, tuple[str, str]]:
        entries: dict[str, tuple[str, str]] = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or "=" not in line:
                continue
            key, value = (s.strip() for s in line.split("=", 1))
            key = unicodedata.normalize("NFC", key).replace("״", '"').replace("׳", "'")
            if not key or not value:
                continue
            if value.startswith("/") and value.endswith("/") and len(value) > 2:
                entries[key] = ("ipa", value[1:-1].strip())
            elif _POINTS.search(value):
                try:
                    entries[key] = ("ipa", ipa_from_nikud(value))
                except Exception:
                    entries[key] = ("text", _POINTS.sub("", value))
            else:
                entries[key] = ("text", value)
        return entries

    def lookup(self, word: str) -> tuple[str, str] | None:
        """The entry for a word, or for the word behind a prefix (ב, ו, ה, ל, מ, ש, כ and their pairs)."""
        entries = self.entries()
        if word in entries:
            return entries[word]
        for length in (3, 2, 1):
            prefix, stem = word[:length], word[length:]
            if len(stem) >= 2 and prefix in PREFIX_IPA and stem in entries:
                kind, value = entries[stem]
                if kind == "ipa":
                    return "ipa", PREFIX_IPA[prefix] + value
                return "text", prefix + value
        return None


_lexicon = Lexicon()


_BARE_PREFIX = re.compile(rf"^([{HEBREW}])(?=[{HEBREW}][֑-ׇ])")
_PREFIX_VOWEL = {"ה": "ַ", "ו": "ְ", "ב": "ְ", "ל": "ְ", "כ": "ְ", "מ": "ֵ", "ש": "ֶ"}


def ipa_from_nikud(word: str) -> str:
    """A pointed word read by phonikud's rules. The stress mark U+05AB after a letter sets the stressed syllable;
    without it the rules stress the last one (so a segolate like סֵ֫פֶר needs the mark). A prefix letter left
    without a point in front of a pointed word (הסֵּפֶר) gets its usual vowel, so it is not read as a bare consonant."""
    import phonikud

    match = _BARE_PREFIX.match(word)
    if match and match.group(1) in _PREFIX_VOWEL:
        word = match.group(1) + _PREFIX_VOWEL[match.group(1)] + word[1:]
    phonemes = phonikud.phonemize(word, use_expander=False)
    return " ".join(phonemes.split())


def settle_words(text: str, text_only: bool = False) -> str:
    """Lexicon replacements and pointed words, each becoming IPA the model passes through, or plain text.
    With text_only, just the plain-text entries (abbreviations): the words stay Hebrew for the number pass."""
    out = []
    for token in text.split():
        lead, core, trail = _split_token(token)
        if not core:
            out.append(token)
            continue
        if _POINTS.search(core):
            if text_only:
                out.append(token)
                continue
            try:
                out.append(lead + ipa_from_nikud(core) + trail)
            except Exception:
                out.append(lead + _POINTS.sub("", core) + trail)
            continue
        found = _lexicon.lookup(core)
        if found is None or (text_only and found[0] != "text"):
            out.append(token)
            continue
        out.append(lead + found[1] + trail)
    return " ".join(out)


def prepare(text: str) -> str:
    """The text as the Hebrew G2P should receive it."""
    text = normalize_symbols(text)
    # abbreviations first, as words: "5 ק"מ" must be "5 קילומטר" when the number pass looks for its noun
    text = settle_words(text, text_only=True)
    text = speak_numbers(text)
    return settle_words(text)  # the lexicon's IPA, pointed words, and a prefix the numbers glued on


if __name__ == "__main__":  # pragma: no cover - a quick look: python hebrew_text.py "טקסט"
    import sys

    for argument in sys.argv[1:] or ["יש לי 3 ימים ו-2 שעות עד ה-15.10.2026, ב-9:30, עם 1,200 שחקנים ו-15%."]:
        print(prepare(argument))
