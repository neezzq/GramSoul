"""Nickname validation and normalisation.

The display form keeps the user's original spelling. Uniqueness and search use
``nick_key``: case-folded, ``ё`` → ``е`` and Cyrillic letters that look like
Latin ones mapped to their Latin twin, so ``Mira``, ``mira`` and ``Мira`` (with
a Cyrillic М) are all the same nickname and nobody can impersonate a friend
with a look-alike."""
from __future__ import annotations

import re
import unicodedata

MIN_LEN = 3
MAX_LEN = 20

_ALLOWED = re.compile(r"^[A-Za-z0-9_А-яЁё]+$")

# Cyrillic → Latin look-alikes (lower case, after casefold)
_CONFUSABLES = str.maketrans({
    "а": "a", "в": "b", "е": "e", "ё": "e", "к": "k", "м": "m", "н": "h",
    "о": "o", "р": "p", "с": "c", "т": "t", "у": "y", "х": "x", "і": "i",
})


class NickError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def clean(raw: str) -> str:
    nick = unicodedata.normalize("NFC", (raw or "").strip())
    return nick


def validate(raw: str) -> str:
    nick = clean(raw)
    if not nick:
        raise NickError("nick_empty", "Введи ник.")
    if len(nick) < MIN_LEN:
        raise NickError("nick_too_short", f"Ник должен быть не короче {MIN_LEN} символов.")
    if len(nick) > MAX_LEN:
        raise NickError("nick_too_long", f"Ник должен быть не длиннее {MAX_LEN} символов.")
    if " " in nick:
        raise NickError("nick_invalid", "В нике не должно быть пробелов. Можно использовать «_».")
    if not _ALLOWED.match(nick):
        raise NickError(
            "nick_invalid",
            "Можно использовать только буквы (латиница или кириллица), цифры и «_».",
        )
    if nick.strip("_") == "":
        raise NickError("nick_invalid", "Ник не может состоять только из «_».")
    return nick


def key(nick: str) -> str:
    """Normalised key used for uniqueness and exact search."""
    k = unicodedata.normalize("NFC", nick.strip()).casefold()
    return k.translate(_CONFUSABLES)
