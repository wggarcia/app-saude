"""
Email domain validation for B2B/B2G self-service registration.
Blocks free/consumer email providers; allows corporate and government domains.
Demo accounts (soluscrt.com / soluscrt.com.br / demo.local) bypass verification.
"""
from __future__ import annotations

# Domains that get immediate verification bypass (internal / demo)
DEMO_DOMAINS = frozenset({
    "soluscrt.com",
    "soluscrt.com.br",
    "demo.local",
    "example.com",   # test-suite emails
})

# Government TLD suffixes valid for Brazil B2G
GOV_SUFFIXES = (
    ".gov.br",
    ".jus.br",
    ".leg.br",
    ".mp.br",
    ".def.br",
    ".mil.br",
    ".eb.mil.br",
    ".marinha.mil.br",
    ".fab.mil.br",
    ".tc.br",        # Tribunal de Contas
    ".tcu.gov.br",
    ".edu.br",
)

# Free / consumer providers — blocked for self-service B2B registration
FREE_DOMAINS = frozenset({
    "gmail.com", "googlemail.com",
    "hotmail.com", "hotmail.com.br", "hotmail.es", "hotmail.it",
    "hotmail.fr", "hotmail.de", "hotmail.co.uk", "hotmail.co.jp",
    "outlook.com", "outlook.com.br", "outlook.es", "outlook.fr",
    "outlook.de", "outlook.it", "outlook.co.uk", "outlook.jp",
    "live.com", "live.com.br", "live.fr", "live.de", "live.co.uk",
    "yahoo.com", "yahoo.com.br", "yahoo.co.uk", "yahoo.es",
    "yahoo.fr", "yahoo.de", "yahoo.co.jp", "yahoo.com.ar",
    "msn.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com",
    "protonmail.com", "proton.me", "pm.me",
    "tutanota.com", "tutamail.com", "tuta.io", "keemail.me",
    "mail.com", "inbox.com",
    "yandex.com", "yandex.ru",
    "bol.com.br", "ig.com.br", "uol.com.br", "terra.com.br",
    "r7.com", "oi.com.br", "globo.com", "globomail.com",
    "gmx.com", "gmx.net", "gmx.de", "gmx.at", "gmx.ch",
    "web.de", "freenet.de",
    "mailinator.com", "guerrillamail.com", "tempmail.com",
    "throwam.com", "sharklasers.com", "yopmail.com",
    "trashmail.com", "dispostable.com", "mailnull.com",
    "10minutemail.com", "10minutemail.net",
    "fakeinbox.com", "maildrop.cc", "getairmail.com",
    "getnada.com", "spam4.me", "spamgourmet.com",
    "trashmail.at", "trashmail.io", "mailnesia.com",
    "discard.email", "spamhereplease.com",
    "zoho.com",   # public Zoho accounts — internal Zoho is company domain
})


def _domain(email: str) -> str:
    """Return lowercased domain from email, or '' on bad format."""
    try:
        return email.split("@", 1)[1].strip().lower()
    except (IndexError, AttributeError):
        return ""


def is_demo_email(email: str) -> bool:
    """True for internal/demo emails that skip the verification step."""
    return _domain(email) in DEMO_DOMAINS


def is_free_email(email: str) -> bool:
    """True if domain belongs to a free/consumer email provider."""
    return _domain(email) in FREE_DOMAINS


def is_government_email(email: str) -> bool:
    """True if domain looks like a Brazilian government / institutional TLD."""
    domain = _domain(email)
    return any(domain.endswith(suffix) for suffix in GOV_SUFFIXES)


def validar_dominio_corporativo(email: str) -> tuple[bool, str]:
    """
    Return (ok, error_message).
    ok=True  → domain is acceptable for self-service registration.
    ok=False → caller should reject with the returned message.
    """
    domain = _domain(email)

    if not domain:
        return False, "E-mail inválido."

    if is_free_email(email):
        return False, (
            "O SolusCRT é uma plataforma B2B e só aceita e-mails corporativos. "
            "Utilize o e-mail da sua empresa ou instituição."
        )

    # Everything else (corporate, government, edu) is acceptable
    return True, ""
