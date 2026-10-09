"""Normalisation et minimisation ; aucun texte privé n'est journalisé."""

import re
import unicodedata


def normalize(value: str) -> str:
    return " ".join("".join(
        char for char in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(char)
    ).split())


SENSITIVE = re.compile(
    r"(?i)\bbearer\s+\S+|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
    r"|\bgsk_[A-Za-z0-9]+|\bAKIA[A-Z0-9]{16}\b|https?://\S+"
    r"|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b(?:\+?\d[ .-]?){9,}\b"
    r"|(?:mot de passe|password|api[_ -]?key|storage[_ -]?key)\s*[:=]\s*\S+"
)


def contains_sensitive(value: str, secrets: tuple[str, ...] = ()) -> bool:
    return bool(SENSITIVE.search(value)) or any(secret and secret in value for secret in secrets)


def display_text(value: str | None) -> str:
    if value is None:
        return "non renseigné"
    value = SENSITIVE.sub("[masqué]", value)
    value = "".join(c if c.isprintable() else " " for c in value)
    value = re.sub(r"[<>\[\]`*_]", "", value)
    return " ".join(value.split())[:160] or "non renseigné"
