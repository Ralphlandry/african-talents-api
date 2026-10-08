def mask_phone(phone: str) -> str:
    """Masque tout sauf les 2 derniers chiffres — utilisé quand l'utilisateur n'a pas payments.view_sensitive."""
    if not phone or len(phone) <= 4:
        return "••••"
    return f"{'•' * (len(phone) - 2)}{phone[-2:]}"
