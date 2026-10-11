#!/usr/bin/env python3
"""Builds the menu translations and their fonts (DolphinNoGUI/PS4Lang.cpp).

xmb/lang/keys.txt has the English texts, xmb/lang/src/<code>.txt the translations in the same
order and sections ("# ---" lines). This writes xmb/lang/<code>.ini ("English = translation") and,
for Japanese, Chinese and Korean, small fonts with only the characters the menus use:
xmb/fonts/NotoSans{JP,SC,KR}-{Regular,Bold}.ttf, cut from Google's Noto Sans variable fonts
(SIL Open Font License; downloaded to ~/dolphinps4-build/tools/noto).

  make-lang.py            check and write the .ini files and the fonts
Needs fontTools for the fonts (~/dolphinps4-build/tools/fontenv: python3 -m venv + pip install
fonttools).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LANG = os.path.join(HERE, "..", "xmb", "lang")
FONTS = os.path.join(HERE, "..", "xmb", "fonts")
NOTO = os.path.expanduser("~/dolphinps4-build/tools/noto")
CJK = {"ja": "JP", "zh": "SC", "ko": "KR"}
# Settings -> Language shows every language in its own script.
LANGUAGE_NAMES = "English Español Français Deutsch Italiano Português Nederlands Polski Türkçe Русский 日本語 中文 (简体) 한국어"
ARABIC_NAME = "العربية"
DEJAVU = "/usr/share/fonts/truetype/dejavu"

# Arabic: the menus draw one glyph per character, so the letters are written here in their joined
# shapes (Arabic Presentation Forms-B: isolated, final, initial, medial) and the short vowel marks
# are left out (nothing positions them over the letters). The text stays in reading order; the
# menus draw each line right to left (PS4Lang.cpp, ReorderRightToLeft).
ARABIC_FORMS = {  # letter: (isolated, final, initial, medial); None: it doesn't join that side
    0x0621: (0xFE80, None, None, None), 0x0622: (0xFE81, 0xFE82, None, None),
    0x0623: (0xFE83, 0xFE84, None, None), 0x0624: (0xFE85, 0xFE86, None, None),
    0x0625: (0xFE87, 0xFE88, None, None), 0x0626: (0xFE89, 0xFE8A, 0xFE8B, 0xFE8C),
    0x0627: (0xFE8D, 0xFE8E, None, None), 0x0628: (0xFE8F, 0xFE90, 0xFE91, 0xFE92),
    0x0629: (0xFE93, 0xFE94, None, None), 0x062A: (0xFE95, 0xFE96, 0xFE97, 0xFE98),
    0x062B: (0xFE99, 0xFE9A, 0xFE9B, 0xFE9C), 0x062C: (0xFE9D, 0xFE9E, 0xFE9F, 0xFEA0),
    0x062D: (0xFEA1, 0xFEA2, 0xFEA3, 0xFEA4), 0x062E: (0xFEA5, 0xFEA6, 0xFEA7, 0xFEA8),
    0x062F: (0xFEA9, 0xFEAA, None, None), 0x0630: (0xFEAB, 0xFEAC, None, None),
    0x0631: (0xFEAD, 0xFEAE, None, None), 0x0632: (0xFEAF, 0xFEB0, None, None),
    0x0633: (0xFEB1, 0xFEB2, 0xFEB3, 0xFEB4), 0x0634: (0xFEB5, 0xFEB6, 0xFEB7, 0xFEB8),
    0x0635: (0xFEB9, 0xFEBA, 0xFEBB, 0xFEBC), 0x0636: (0xFEBD, 0xFEBE, 0xFEBF, 0xFEC0),
    0x0637: (0xFEC1, 0xFEC2, 0xFEC3, 0xFEC4), 0x0638: (0xFEC5, 0xFEC6, 0xFEC7, 0xFEC8),
    0x0639: (0xFEC9, 0xFECA, 0xFECB, 0xFECC), 0x063A: (0xFECD, 0xFECE, 0xFECF, 0xFED0),
    0x0640: (0x0640, 0x0640, 0x0640, 0x0640),
    0x0641: (0xFED1, 0xFED2, 0xFED3, 0xFED4), 0x0642: (0xFED5, 0xFED6, 0xFED7, 0xFED8),
    0x0643: (0xFED9, 0xFEDA, 0xFEDB, 0xFEDC), 0x0644: (0xFEDD, 0xFEDE, 0xFEDF, 0xFEE0),
    0x0645: (0xFEE1, 0xFEE2, 0xFEE3, 0xFEE4), 0x0646: (0xFEE5, 0xFEE6, 0xFEE7, 0xFEE8),
    0x0647: (0xFEE9, 0xFEEA, 0xFEEB, 0xFEEC), 0x0648: (0xFEED, 0xFEEE, None, None),
    0x0649: (0xFEEF, 0xFEF0, None, None), 0x064A: (0xFEF1, 0xFEF2, 0xFEF3, 0xFEF4),
}
ARABIC_LAM_ALEF = {0x0622: (0xFEF5, 0xFEF6), 0x0623: (0xFEF7, 0xFEF8), 0x0625: (0xFEF9, 0xFEFA),
                   0x0627: (0xFEFB, 0xFEFC)}


def shape_arabic(text):
    chars = [c for c in text if not (0x064B <= ord(c) <= 0x0652 or ord(c) == 0x0670)]
    forms = lambda c: ARABIC_FORMS.get(ord(c)) if c else None
    joins_next = lambda c: bool(forms(c)) and forms(c)[2] is not None  # can join the letter after
    joins_prev = lambda c: bool(forms(c)) and forms(c)[1] is not None  # can join the letter before
    out = []
    i = 0
    while i < len(chars):
        c = chars[i]
        f = forms(c)
        if not f:
            out.append(c)
            i += 1
            continue
        prev = chars[i - 1] if i > 0 else None
        linked_prev = prev is not None and joins_next(prev) and joins_prev(c)
        if ord(c) == 0x0644 and i + 1 < len(chars) and ord(chars[i + 1]) in ARABIC_LAM_ALEF:
            isolated, final = ARABIC_LAM_ALEF[ord(chars[i + 1])]
            out.append(chr(final if linked_prev else isolated))
            i += 2
            continue
        nxt = chars[i + 1] if i + 1 < len(chars) else None
        linked_next = nxt is not None and joins_next(c) and joins_prev(nxt)
        isolated, final, initial, medial = f
        glyph = medial if linked_prev and linked_next else final if linked_prev else \
            initial if linked_next else isolated
        out.append(chr(glyph))
        i += 1
    return "".join(out)


def sections(path):
    """[(section name, [lines])] without comments; sections start at '# ---' lines."""
    out = [("start", [])]
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n").rstrip("\r")
        if line.startswith("# ---"):
            out.append((line[5:].strip(), []))
        elif line.startswith("#") or not line.strip():
            continue
        else:
            out[-1][1].append(line)
    return out


def placeholders(text):
    return len(re.findall(r"\{\d?\}", text))


def build(code, keys):
    trans = sections(os.path.join(LANG, "src", code + ".txt"))
    if [s[0] for s in trans] != [s[0] for s in keys]:
        sys.exit(f"{code}: sections differ: {[s[0] for s in trans]}")
    lines = [f"# {code}: written by scripts/make-lang.py from src/{code}.txt - edit that file"]
    used = set()
    for (name, english), (_, translated) in zip(keys, trans):
        if len(english) != len(translated):
            sys.exit(f"{code}: section '{name}' has {len(translated)} lines, keys.txt {len(english)}")
        for e, t in zip(english, translated):
            if placeholders(e) != placeholders(t):
                sys.exit(f"{code}: placeholders differ:\n  {e}\n  {t}")
            if " = " in e:
                sys.exit(f"' = ' in an English text: {e}")
            if code == "ar":
                t = shape_arabic(t)
            lines.append(f"{e} = {t}")
            used.update(t)
    open(os.path.join(LANG, code + ".ini"), "w", encoding="utf-8", newline="\n").write(
        "\n".join(lines) + "\n")
    print(f"{code}: {len(lines) - 1} texts")
    return used


def make_font(code, chars):
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    from fontTools import subset

    source = os.path.join(NOTO, f"NotoSans{CJK[code]}.ttf")
    text = set(chars) | set(LANGUAGE_NAMES)
    # Kana in full for Japanese (save names, game titles); the rest only as used.
    if code == "ja":
        text |= {chr(c) for c in range(0x3040, 0x3100)}
    text |= {chr(c) for c in range(0x3000, 0x3040)}  # CJK punctuation
    text |= {chr(c) for c in range(0xFF01, 0xFF5F)}  # full-width forms
    for weight, name in ((400, "Regular"), (800, "Bold")):
        font = instancer.instantiateVariableFont(TTFont(source), {"wght": weight})
        options = subset.Options()
        options.layout_features = ["*"]
        options.name_IDs = ["*"]
        subsetter = subset.Subsetter(options)
        subsetter.populate(text="".join(sorted(text)))
        subsetter.subset(font)
        out = os.path.join(FONTS, f"NotoSans{CJK[code]}-{name}.ttf")
        font.save(out)
        print(f"  {os.path.basename(out)}: {os.path.getsize(out) // 1024} KiB, {len(text)} characters")


def make_arabic_font(chars):
    """xmb/fonts/DejaVuSansArabic-{Regular,Bold}.ttf: the Arabic shapes the menus use, cut from
    DejaVu Sans (Bitstream Vera license: free to copy and redistribute; xmb/fonts/LICENSE-DejaVu.txt)."""
    from fontTools.ttLib import TTFont
    from fontTools import subset

    text = {c for c in set(chars) | set(shape_arabic(ARABIC_NAME))
            if 0x0600 <= ord(c) <= 0x06FF or 0xFB50 <= ord(c) <= 0xFEFF}
    text |= {chr(0x060C), chr(0x061B), chr(0x061F)}  # Arabic comma, semicolon, question mark
    for source, name in (("DejaVuSans.ttf", "Regular"), ("DejaVuSans-Bold.ttf", "Bold")):
        font = TTFont(os.path.join(DEJAVU, source))
        options = subset.Options()
        options.layout_features = []
        options.name_IDs = ["*"]
        subsetter = subset.Subsetter(options)
        subsetter.populate(text="".join(sorted(text)))
        subsetter.subset(font)
        out = os.path.join(FONTS, f"DejaVuSansArabic-{name}.ttf")
        font.save(out)
        print(f"  {os.path.basename(out)}: {os.path.getsize(out) // 1024} KiB, {len(text)} characters")


def main():
    keys = sections(os.path.join(LANG, "keys.txt"))
    used = {}
    for name in sorted(os.listdir(os.path.join(LANG, "src"))):
        if name.endswith(".txt"):
            code = name[:-4]
            used[code] = build(code, keys)
    for code in CJK:
        if code in used or True:
            make_font(code, used.get(code, set()))
    make_arabic_font(used.get("ar", set()))
    print("Arabic name (shaped, for PS4Lang.cpp and PS4Settings.cpp):",
          shape_arabic(ARABIC_NAME).encode("utf-8").hex())


if __name__ == "__main__":
    main()
