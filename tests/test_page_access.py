from execution.page_access import enforce_page_access, pages_for_user


ALL_PAGES = [
    "📉 Terminal de Trading",
    "🇧🇷 Terminal B3",
    "🌎 Terminal Global",
    "FX COMMAND CENTER",
    "MONITOR MACRO",
    "🇧🇷 MONITOR BR",
    "RENDAFIXABR",
    "Crypto Terminal",
    "📺 Terminal Bloomberg",
    "WATCHLIST",
]


def test_restricted_account_sees_only_requested_pages():
    assert pages_for_user("FCCARNE@TERRA.COM.BR", ALL_PAGES) == [
        "🇧🇷 Terminal B3",
        "🌎 Terminal Global",
        "MONITOR MACRO",
        "🇧🇷 MONITOR BR",
        "RENDAFIXABR",
        "Crypto Terminal",
        "WATCHLIST",
    ]


def test_other_accounts_keep_full_navigation():
    assert pages_for_user("other@example.com", ALL_PAGES) == ALL_PAGES


def test_disallowed_or_stale_page_falls_back_to_terminal_global():
    assert enforce_page_access(
        "⚙️ Painel de Controle",
        "fccarne@terra.com.br",
        ALL_PAGES,
        "🌎 Terminal Global",
    ) == "🌎 Terminal Global"
