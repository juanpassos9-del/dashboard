"""Page visibility rules for authenticated dashboard accounts."""

RESTRICTED_PAGE_ACCESS = {
    "nidia_nalonm@hotmail.com": frozenset({
        "📉 Terminal de Trading",
        "🇧🇷 Terminal B3",
        "🌎 Terminal Global",
        "MONITOR MACRO",
        "🇧🇷 MONITOR BR",
        "RENDAFIXABR",
        "Crypto Terminal",
    }),
    "fccarne@terra.com.br": frozenset({
        "📉 Terminal de Trading",
        "🇧🇷 Terminal B3",
        "🌎 Terminal Global",
        "MONITOR MACRO",
        "🇧🇷 MONITOR BR",
        "RENDAFIXABR",
        "Crypto Terminal",
        "WATCHLIST",
    }),
}


def pages_for_user(email: str, all_pages: list[str]) -> list[str]:
    allowed = RESTRICTED_PAGE_ACCESS.get((email or "").strip().lower())
    if allowed is None:
        return list(all_pages)
    return [page for page in all_pages if page in allowed]


def enforce_page_access(page: str, email: str, all_pages: list[str], default_page: str) -> str:
    allowed_pages = pages_for_user(email, all_pages)
    if page in allowed_pages:
        return page
    if default_page in allowed_pages:
        return default_page
    return allowed_pages[0] if allowed_pages else default_page
