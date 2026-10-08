"""Assainissement HTML des articles côté serveur (ne jamais faire confiance au HTML envoyé par le client)."""
import nh3

ALLOWED_TAGS = {"p", "br", "strong", "em", "u", "h2", "h3", "ul", "ol", "li", "a", "blockquote", "img"}
ALLOWED_ATTRIBUTES = {"a": {"href", "title", "target"}, "img": {"src", "alt"}}


def sanitize_html(raw: str) -> str:
    if not raw:
        return ""
    return nh3.clean(raw, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, link_rel="nofollow noopener noreferrer")
