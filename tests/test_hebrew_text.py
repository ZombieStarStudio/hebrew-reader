# -*- coding: utf-8 -*-
"""The reading layer, case by case. Run from the HebrewSpeaker folder:

    .venv\\Scripts\\python.exe -X utf8 -m unittest tests.test_hebrew_text -v

No model is loaded: these are the text rules alone (numbers, gender, dates, abbreviations, the lexicon). The
pointed-word cases go through phonikud's rules, which are pure Python.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hebrew_text as h  # noqa: E402


class Cardinal(unittest.TestCase):
    def test_small(self):
        self.assertEqual(h.cardinal(0), "אפס")
        self.assertEqual(h.cardinal(1, "f"), "אחת")
        self.assertEqual(h.cardinal(1, "m"), "אחד")
        self.assertEqual(h.cardinal(2, "f"), "שתיים")
        self.assertEqual(h.cardinal(2, "m"), "שניים")
        self.assertEqual(h.cardinal(15, "f"), "חמש עשרה")
        self.assertEqual(h.cardinal(15, "m"), "חמישה עשר")
        self.assertEqual(h.cardinal(21, "f"), "עשרים ואחת")
        self.assertEqual(h.cardinal(21, "m"), "עשרים ואחד")

    def test_hundreds_and_thousands(self):
        self.assertEqual(h.cardinal(100), "מאה")
        self.assertEqual(h.cardinal(110), "מאה ועשר")
        self.assertEqual(h.cardinal(123, "f"), "מאה עשרים ושלוש")
        self.assertEqual(h.cardinal(218, "f"), "מאתיים ושמונה עשרה")
        self.assertEqual(h.cardinal(1000), "אלף")
        self.assertEqual(h.cardinal(1200), "אלף ומאתיים")
        self.assertEqual(h.cardinal(1500), "אלף וחמש מאות")
        self.assertEqual(h.cardinal(2026, "f"), "אלפיים עשרים ושש")
        self.assertEqual(h.cardinal(2026, "m"), "אלפיים עשרים ושישה")
        self.assertEqual(h.cardinal(3000), "שלושת אלפים")
        self.assertEqual(h.cardinal(21000), "עשרים ואחד אלף")
        self.assertEqual(h.cardinal(1990), "אלף תשע מאות ותשעים")

    def test_millions(self):
        self.assertEqual(h.cardinal(1_000_000), "מיליון")
        self.assertEqual(h.cardinal(2_500_000), "שני מיליון וחמש מאות אלף")
        self.assertEqual(h.cardinal(3_000_000), "שלושה מיליון")
        self.assertEqual(h.cardinal(1_000_001, "f"), "מיליון ואחת")


class Gender(unittest.TestCase):
    def test_counted_nouns(self):
        self.assertEqual(h.prepare("יש לי 3 ימים ו-2 שעות"), "יש לי שלושה ימים ושתי שעות")
        self.assertEqual(h.prepare("21 ימים, 22 שעות"), "עשרים ואחד ימים, עשרים ושתיים שעות")
        self.assertEqual(h.prepare("2 פעמים, 3 שנים, 2 ערים"), "שתי פעמים, שלוש שנים, שתי ערים")
        self.assertEqual(h.prepare("3 לילות, 4 שולחנות"), "שלושה לילות, ארבעה שולחנות")
        self.assertEqual(h.prepare("1200 שחקנים"), "אלף ומאתיים שחקנים")

    def test_one_moves_after_its_noun(self):
        self.assertEqual(h.prepare("1 שעה"), "שעה אחת")
        self.assertEqual(h.prepare("1 יום"), "יום אחד")
        self.assertEqual(h.prepare("ו-1 שקל עודף"), "ושקל אחד עודף")
        self.assertEqual(h.prepare("1 שקלים"), "שקל אחד")
        self.assertEqual(h.prepare("1 פעם"), "פעם אחת")

    def test_construct_before_definite(self):
        self.assertEqual(h.prepare("3 הימים"), "שלושת הימים")
        self.assertEqual(h.prepare("2 הבנות"), "שתי הבנות")
        self.assertEqual(h.prepare("4 השעות"), "ארבע השעות")

    def test_labels_after_a_noun(self):
        self.assertEqual(h.prepare("שלב 3"), "שלב שלוש")
        self.assertEqual(h.prepare("שלב 1, רמה 1"), "שלב אחד, רמה אחת")
        self.assertEqual(h.prepare("שלב 1 קל"), "שלב אחד קל")
        self.assertEqual(h.prepare("יש לי 1 שעה"), "יש לי שעה אחת")
        self.assertEqual(h.prepare("ו-1 פיצ'ר חדש"), "vefˈitʃeʁ אחד חדש")  # the lexicon reads the glued word
        self.assertEqual(h.prepare("יש לי 1 שעה ו-1 פיצ'ר חדש"), "יש לי שעה אחת vefˈitʃeʁ אחד חדש")
        self.assertEqual(h.prepare("3 ימים ב-3 שקלים"), "שלושה ימים בשלושה שקלים")
        self.assertEqual(h.prepare("גרסה 218 של ההאב"), "גרסה מאתיים ושמונה עשרה של hahˈab")
        self.assertEqual(h.prepare("עמוד 12"), "עמוד שתים עשרה")
        self.assertEqual(h.prepare("יש 3 בבוקר"), "יש שלוש בבוקר")

    def test_ordinals(self):
        self.assertEqual(h.prepare("בפעם ה-3"), "בפעם השלישית")
        self.assertEqual(h.prepare("השלב ה-2 קשה"), "השלב השני קשה")
        self.assertEqual(h.prepare("הפרק ה-15"), "הפרק החמישה עשר")

    def test_percent_and_money(self):
        self.assertEqual(h.prepare("עלה ב-15%"), "עלה בחמישה עשר אחוז")
        self.assertEqual(h.prepare("1%, 100%"), "אחוז אחד, מאה אחוז")
        self.assertEqual(h.prepare("50 שקלים"), "חמישים שקלים")
        self.assertEqual(h.prepare("3 ש\"ח"), "שלושה שקלים")
        self.assertEqual(h.prepare("₪50, 50$"), "חמישים שקלים, חמישים דולר")
        self.assertEqual(h.prepare("3 מיליון שקלים"), "שלושה מיליון שקלים")
        self.assertEqual(h.prepare("3 אלף"), "שלושת אלפים")
        self.assertEqual(h.prepare("2003 שקלים"), "אלפיים ושלושה שקלים")

    def test_units(self):
        self.assertEqual(h.prepare("5 ק\"מ, 10 ס\"מ"), "חמישה קילומטר, עשרה סנטימטר")
        self.assertEqual(h.prepare("25°"), "עשרים וחמש מעלות")


class DatesAndTimes(unittest.TestCase):
    def test_dates_are_masculine(self):
        self.assertEqual(h.prepare("ב-15.10.2026"), "בחמישה עשר באוקטובר אלפיים עשרים ושש")
        self.assertEqual(h.prepare("2026-10-15"), "חמישה עשר באוקטובר אלפיים עשרים ושש")
        self.assertEqual(h.prepare("ה-15 באוקטובר"), "החמישה עשר באוקטובר")
        self.assertEqual(h.prepare("ה-1 בינואר"), "האחד בינואר")
        self.assertEqual(h.prepare("מה-3 עד ה-5 במאי"), "מהשלושה עד החמישה במאי")
        self.assertEqual(h.prepare("15 אוקטובר"), "חמישה עשר אוקטובר")

    def test_times_are_feminine(self):
        self.assertEqual(h.prepare("בשעה 9:30"), "בשעה תשע ושלושים")
        self.assertEqual(h.prepare("14:30, 21:00"), "ארבע עשרה ושלושים, עשרים ואחת")
        self.assertEqual(h.prepare("ב-9:30"), "בתשע ושלושים")
        self.assertEqual(h.prepare("12 ו-30"), "שתים עשרה ושלושים")  # what the hub sends for 12:30

    def test_years(self):
        self.assertEqual(h.prepare("ב-2026"), "באלפיים עשרים ושש")
        self.assertEqual(h.prepare("בשנת 1990"), "בשנת אלף תשע מאות ותשעים")


class OtherNumbers(unittest.TestCase):
    def test_ranges_and_decimals(self):
        self.assertEqual(h.prepare("3-5 ימים"), "שלושה עד חמישה ימים")
        self.assertEqual(h.prepare("3 או 4 שעות"), "שלוש או ארבע שעות")
        self.assertEqual(h.prepare("3.5 שעות"), "שלוש וחצי שעות")
        self.assertEqual(h.prepare("0.5 אחוז"), "חצי אחוז")
        self.assertEqual(h.prepare("3.14"), "שלוש נקודה אחת ארבע")
        self.assertEqual(h.prepare("גרסה 1.2.3"), "גרסה אחת נקודה שתיים נקודה שלוש")

    def test_phones_and_codes(self):
        self.assertEqual(h.prepare("054-1234567"), "אפס חמש ארבע, אחת שתיים שלוש ארבע חמש שש שבע")
        self.assertEqual(h.prepare("0541234567"), "אפס חמש ארבע, אחת שתיים שלוש ארבע חמש שש שבע")

    def test_negative_and_symbols(self):
        self.assertEqual(h.prepare("-3 מעלות"), "מינוס שלוש מעלות")
        self.assertEqual(h.prepare("#3, 7+"), "מספר שלוש, שבע פלוס")
        self.assertEqual(h.prepare("בית-ספר"), "בית ספר")
        self.assertEqual(h.prepare("ב-"), "ב")  # what the English split leaves of "ב-Unity"


class LexiconAndNikud(unittest.TestCase):
    def test_abbreviations(self):
        self.assertEqual(h.prepare("ארה\"ב, סה\"כ 7 דברים"), "ארצות הברית, סך הכול שבעה דברים")
        self.assertEqual(h.prepare("בארה\"ב"), "בארצות הברית")
        self.assertEqual(h.prepare("וכו', מס' 5, ד\"ר כהן"), "וכולי, מספר חמש, דוקטור כהן")
        self.assertEqual(h.prepare("צה״ל"), "tsˈahal")  # Hebrew gershayim, not the ASCII quote

    def test_ipa_entries_and_prefixes(self):
        self.assertEqual(h.prepare("הדוח"), "hadˈuaχ")
        self.assertEqual(h.prepare("בדוח, להאב, מההאב"), "bedˈuaχ, lehˈab, mehahˈab")
        self.assertEqual(h.prepare("פיקסל ארט"), "pˈiksel ˈaʁt")  # ארט is in the lexicon since 16.10
        self.assertEqual(h.prepare("3 דוחות"), "שלושה duχˈot")  # the noun is still Hebrew when the number looks
        self.assertEqual(h.prepare("3 סְפָרִים"), "שלושה sfaʁˈim")

    def test_pointed_words(self):
        self.assertEqual(h.prepare("שֶׁ֫לִי עובדת"), "ʃˈeli עובדת")
        self.assertEqual(h.prepare("הַסַּפָּר"), "hasapˈaʁ")
        self.assertEqual(h.prepare("הסֵּ֫פֶר"), "hasˈefeʁ")  # a bare prefix letter gets its vowel

    def test_plain_text_untouched(self):
        self.assertEqual(h.prepare("שלום, מה שלומך?"), "שלום, מה שלומך?")


if __name__ == "__main__":
    unittest.main()
