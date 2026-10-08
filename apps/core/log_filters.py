"""Filtre de logs masquant les secrets (clés HR-Skills Pay, jetons, mots de passe)."""
import logging
import os
import re

_PATTERNS = [
    re.compile(r"hrsk_(?:pk|sk)_(?:test|live)_[A-Za-z0-9_\-]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)(['\"]?\s*[:=]\s*['\"]?)[^\s'\",}]+"),
]
_SECRET_ENV_NAMES = ("SECRET_KEY", "JWT_SIGNING_KEY", "HRSKILLS_SECRET_KEY", "HRSKILLS_PUBLIC_KEY", "HRSKILLS_WEBHOOK_SECRET")


def redact(text: str) -> str:
    for name in _SECRET_ENV_NAMES:
        value = os.environ.get(name)
        if value and len(value) >= 8:
            text = text.replace(value, "***")
    text = _PATTERNS[0].sub("***", text)
    text = _PATTERNS[1].sub("Bearer ***", text)
    text = _PATTERNS[2].sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)
    return text


class SecretRedactingFilter(logging.Filter):
    def filter(self, record):
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:  # ne jamais bloquer un log
            pass
        return True
