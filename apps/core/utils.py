from django.conf import settings


def get_client_ip(request):
    """
    IP du client. L'en-tête X-Forwarded-For n'est utilisé que si NUM_PROXIES > 0
    (nombre de reverse-proxies de confiance), en lisant depuis la droite pour
    empêcher un client de falsifier son adresse.
    """
    if request is None:
        return None
    remote = request.META.get("REMOTE_ADDR")
    num_proxies = getattr(settings, "NUM_PROXIES", 0)
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if not num_proxies or not xff:
        return remote
    addrs = [a.strip() for a in xff.split(",") if a.strip()]
    if not addrs:
        return remote
    return addrs[-min(num_proxies, len(addrs))]


def get_user_agent(request):
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")[:255]
