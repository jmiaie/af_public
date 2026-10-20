"""
Shared HTTP helpers for the LLM providers.

``urllib.request.urlopen`` accepts ``file:``, ``ftp:``, ``data:`` and any
other scheme with a registered handler. Provider base URLs come from
constructor arguments and environment variables, so every call site checks
the URL with :func:`require_http_url` before opening it.
"""

from typing import Union
from urllib.parse import urlsplit
from urllib.request import Request

ALLOWED_SCHEMES = frozenset({"http", "https"})


def require_http_url(target: Union[str, Request]) -> str:
    """Reject any URL whose scheme is not ``http`` or ``https``.

    Args:
        target: A URL string or a :class:`urllib.request.Request`.

    Returns:
        The validated URL string.

    Raises:
        ValueError: If the scheme is missing or not ``http``/``https``. The
            message names only the scheme, never the full URL, because some
            provider URLs carry an API key in the query string.
    """
    url = target.full_url if isinstance(target, Request) else target
    scheme = urlsplit(url).scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError(
            f"Refusing to open URL with scheme {scheme or '(none)'!r}; "
            "only http and https are allowed"
        )
    return url
