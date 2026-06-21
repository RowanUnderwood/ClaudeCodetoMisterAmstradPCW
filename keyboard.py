"""Keyboard fallback (plan section 9) - only used when auto-run isn't viable.

Sends a string to the running core one key at a time via
POST /api/controls/keyboard-raw/{code}, where a leading '-' means hold Shift.
Codes are Linux uinput keycodes. The map is built programmatically.

NOTE: PCW-core punctuation mapping may differ from a standard US layout.
Letters/digits/space (all that 'BASIC PROG' needs) are safe; verify symbols
like ':' interactively before relying on 'BASIC B:PROG'.
"""

import time

import config
import device

ENTER = 28
SPACE = 57

# base (unshifted) uinput keycodes
_LETTERS = {
    "a": 30, "b": 48, "c": 46, "d": 32, "e": 18, "f": 33, "g": 34, "h": 35,
    "i": 23, "j": 36, "k": 37, "l": 38, "m": 50, "n": 49, "o": 24, "p": 25,
    "q": 16, "r": 19, "s": 31, "t": 20, "u": 22, "v": 47, "w": 17, "x": 45,
    "y": 21, "z": 44,
}
_DIGITS = {"1": 2, "2": 3, "3": 4, "4": 5, "5": 6,
           "6": 7, "7": 8, "8": 9, "9": 10, "0": 11}
_SYMBOLS = {
    "-": 12, "=": 13, "[": 26, "]": 27, ";": 39, "'": 40, "`": 41,
    "\\": 43, ",": 51, ".": 52, "/": 53,
}
# characters reached by holding Shift, mapped to their base key char
_SHIFTED = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7",
    "*": "8", "(": "9", ")": "0", "_": "-", "+": "=", "{": "[", "}": "]",
    ":": ";", '"': "'", "~": "`", "|": "\\", "<": ",", ">": ".", "?": "/",
}


def _code_for(ch):
    """Return (keycode, shift?) for a character, or (None, False) if unknown."""
    if ch == " ":
        return SPACE, False
    low = ch.lower()
    if low in _LETTERS:
        return _LETTERS[low], ch.isupper()
    if ch in _DIGITS:
        return _DIGITS[ch], False
    if ch in _SYMBOLS:
        return _SYMBOLS[ch], False
    if ch in _SHIFTED:
        base = _SHIFTED[ch]
        code = _DIGITS.get(base) or _SYMBOLS.get(base)
        return code, True
    return None, False


def _send_raw(code):
    device._post(f"/api/controls/keyboard-raw/{code}")


def send_key(code, shift=False):
    _send_raw(f"-{code}" if shift else f"{code}")


def send_string(text, enter=True, delay=0.06):
    """Type text key-by-key; optionally press Enter at the end."""
    for ch in text:
        code, shift = _code_for(ch)
        if code is None:
            raise ValueError(f"No keycode mapping for character {ch!r}")
        send_key(code, shift)
        time.sleep(delay)
    if enter:
        send_key(ENTER)
        time.sleep(delay)


def run_basic(prog="PROG", drive=""):
    """Type the run command, e.g. 'BASIC PROG' or 'BASIC B:PROG'."""
    cmd = f"{config.RUN_LINE.split()[0]} {drive}{prog}"
    send_string(cmd, enter=True)
