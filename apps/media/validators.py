"""Validation des fichiers uploadés : extension + type MIME réel (pas seulement le nom) + taille."""
from django.core.exceptions import ValidationError

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/webp": [".webp"],
    "image/gif": [".gif"],
}
ALLOWED_DOCUMENT_TYPES = {"application/pdf": [".pdf"]}

MAX_IMAGE_SIZE_BYTES = 8 * 1024 * 1024   # 8 Mo
MAX_DOCUMENT_SIZE_BYTES = 15 * 1024 * 1024  # 15 Mo


def _sniff_mime(file_obj):
    """Détecte le type réel à partir des premiers octets (signature), sans dépendance externe."""
    head = file_obj.read(16)
    file_obj.seek(0)
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[0:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "image/gif"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def validate_upload(file_obj, filename):
    import os

    ext = os.path.splitext(filename)[1].lower()
    mime = _sniff_mime(file_obj)
    allowed = {**ALLOWED_IMAGE_TYPES, **ALLOWED_DOCUMENT_TYPES}

    if mime not in allowed:
        raise ValidationError("Type de fichier non autorisé. Formats acceptés : JPG, PNG, WEBP, GIF, PDF.")
    if ext not in allowed[mime]:
        raise ValidationError("L'extension du fichier ne correspond pas à son contenu réel.")

    max_size = MAX_DOCUMENT_SIZE_BYTES if mime in ALLOWED_DOCUMENT_TYPES else MAX_IMAGE_SIZE_BYTES
    if file_obj.size > max_size:
        raise ValidationError(f"Fichier trop volumineux (max {max_size // (1024 * 1024)} Mo).")

    return mime, ("image" if mime in ALLOWED_IMAGE_TYPES else "document")
