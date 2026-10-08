from celery import shared_task


@shared_task
def expire_stale_pending_payments():
    from .services import expire_stale_pending_payments as _expire

    return _expire()
