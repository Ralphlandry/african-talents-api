from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    scope = "login"


class RefreshRateThrottle(AnonRateThrottle):
    scope = "refresh"


class VoteOrderRateThrottle(AnonRateThrottle):
    """Limite la création de commandes de vote par IP (voir aussi apps/publicapi/views.py)."""

    scope = "vote_order"
