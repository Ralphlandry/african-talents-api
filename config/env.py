"""Lecture des variables d'environnement (aucun secret n'est jamais codé en dur)."""
import os
import re
from datetime import timedelta


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and (value is None or str(value).strip() == ""):
        raise RuntimeError(f"Variable d'environnement obligatoire manquante : {name}")
    return value


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default=0):
    value = os.environ.get(name)
    return default if value is None or value.strip() == "" else int(value)


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


_DURATION = re.compile(r"^\s*(\d+)\s*([smhd])\s*$", re.IGNORECASE)
_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def env_duration(name, default):
    """Accepte '15m', '7d', '2h', '30s'."""
    raw = os.environ.get(name, default)
    match = _DURATION.match(raw)
    if not match:
        raise RuntimeError(f"{name} invalide ({raw!r}) : utilisez par ex. 15m, 2h, 7d.")
    return timedelta(**{_UNITS[match.group(2).lower()]: int(match.group(1))})
