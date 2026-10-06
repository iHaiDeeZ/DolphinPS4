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


if __name__ == "__main__":
    main()
