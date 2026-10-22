from django.db import transaction

from apps.audit.constants import AuditAction, AuditModule
from apps.audit.services import record
from apps.core.exceptions import UnprocessableError

from .models import MediaAsset
from .validators import validate_upload


@transaction.atomic
def upload_media(actor, *, file_obj, usage="", request=None):
    try:
        mime, kind = validate_upload(file_obj, file_obj.name)
    except Exception as exc:  # ValidationError Django -> erreur API homogène
        raise UnprocessableError(str(getattr(exc, "message", exc)), code="INVALID_FILE")

    asset = MediaAsset.objects.create(
        file=file_obj, original_name=file_obj.name[:255], kind=kind, mime_type=mime,
        size_bytes=file_obj.size, usage=usage, uploaded_by=actor,
    )
    record(request=request, actor=actor, action=AuditAction.MEDIA_UPLOADED, module=AuditModule.MEDIA,
           resource="media_asset", resource_id=asset.pk, metadata={"name": asset.original_name, "kind": kind})
    return asset


@transaction.atomic
def delete_media(actor, asset, *, request=None):
    name, pk = asset.original_name, asset.pk
    asset.delete()
    record(request=request, actor=actor, action=AuditAction.MEDIA_DELETED, module=AuditModule.MEDIA,
           resource="media_asset", resource_id=pk, metadata={"name": name})
