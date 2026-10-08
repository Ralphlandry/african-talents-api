from celery import shared_task


@shared_task
def publish_scheduled_news():
    from .services import publish_due_scheduled_posts

    return publish_due_scheduled_posts()
