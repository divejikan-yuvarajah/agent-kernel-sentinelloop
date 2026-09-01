"""Authenticated Shell contract tests."""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "dashboard" / "frontend"
SHELL = FRONTEND / "src" / "components" / "Shell"


def test_shell_components_exist():
    required = [
        "Shell.tsx",
        "TopNav.tsx",
        "MobileNav.tsx",
        "Sidebar.tsx",
        "Breadcrumbs.tsx",
        "RouterStatusPill.tsx",
        "NotificationCenter.tsx",
        "PageContainer.tsx",
        "UserMenu.tsx",
        "PageHeader.tsx",
        "PageLoading.tsx",
        "ErrorState.tsx",
        "EmptyState.tsx",
    ]
    for name in required:
        assert (SHELL / name).is_file(), name


def test_appshell_delegates_to_unified_shell():
    appshell = (FRONTEND / "design-system" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    assert "from \"@/components/Shell\"" in appshell or "components/Shell" in appshell
    assert "Shell" in appshell
    shell = (SHELL / "Shell.tsx").read_text(encoding="utf-8")
    assert "TopNav" in shell
    assert "Breadcrumbs" in shell
    assert "Emergency Command Center" not in shell  # stays in Sidebar component
    sidebar = (FRONTEND / "design-system" / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
    assert "Emergency Command Center" in sidebar


def test_primary_navigation_routes():
    nav = (SHELL / "shellNav.ts").read_text(encoding="utf-8")
    top = (SHELL / "TopNav.tsx").read_text(encoding="utf-8")
    mobile = (SHELL / "MobileNav.tsx").read_text(encoding="utf-8")
    assert "SHELL_MOBILE_EXTRA" in nav
    assert "SENTINELLOOP" in top
    assert "sl-topnav__links" not in top
    assert "Dashboard" in mobile or "SHELL_MOBILE_EXTRA" in mobile
    assert "Settings" in mobile or "SHELL_MOBILE_EXTRA" in mobile
    assert "/ai-usage" not in nav
    assert "Router Status" not in nav
    assert "Predictions" not in nav


def test_router_status_pill_uses_endpoint_and_semantic_tones():
    pill = (SHELL / "RouterStatusPill.tsx").read_text(encoding="utf-8")
    css = (FRONTEND / "src" / "styles" / "shell.css").read_text(encoding="utf-8")
    assert "fetchRouterStatus" in pill
    assert "AI Usage Details" in pill
    assert "Current Model" in pill
    assert "Remaining Budget" in pill
    assert "--verified-teal" in css
    assert "--signal-amber" in css
    assert "--hazard-red" in css
    assert "sl-router-pill--ok" in css
    assert "sl-router-pill--warn" in css
    assert "sl-router-pill--down" in css


def test_system_indicators_and_notifications():
    indicators = (SHELL / "SystemIndicators.tsx").read_text(encoding="utf-8")
    notify = (SHELL / "NotificationCenter.tsx").read_text(encoding="utf-8")
    assert "fetchSystemHealth" in indicators
    assert "Telegram" in indicators and "Slack" in indicators
    assert "Database" in indicators and "AI Router" in indicators
    assert "Notification" in notify or "notifications" in notify


def test_responsive_mobile_menu_and_reduced_motion():
    mobile = (SHELL / "MobileNav.tsx").read_text(encoding="utf-8")
    css = (FRONTEND / "src" / "styles" / "shell.css").read_text(encoding="utf-8")
    shell = (SHELL / "Shell.tsx").read_text(encoding="utf-8")
    assert "Menu" in mobile or "mobile" in mobile.lower()
    assert "sl-mobile-nav" in css
    assert "prefers-reduced-motion" in css
    assert "Escape" in shell


def test_page_container_and_states():
    container = (SHELL / "PageContainer.tsx").read_text(encoding="utf-8")
    loading = (SHELL / "PageLoading.tsx").read_text(encoding="utf-8")
    error = (SHELL / "ErrorState.tsx").read_text(encoding="utf-8")
    empty = (SHELL / "EmptyState.tsx").read_text(encoding="utf-8")
    css = (FRONTEND / "src" / "styles" / "shell.css").read_text(encoding="utf-8")
    assert "sl-page-container" in container
    assert "1440px" in css or "1280px" in css or "--content-max" in css
    assert "Retry" in error
    assert "sl-page-loading" in loading
    assert "sl-empty-state" in empty


def test_theme_tokens_and_no_old_palette_in_shell_css():
    css = (FRONTEND / "src" / "styles" / "shell.css").read_text(encoding="utf-8")
    tokens = (FRONTEND / "design-system" / "tokens.css").read_text(encoding="utf-8")
    for token in (
        "--ink",
        "--panel",
        "--panel-raised",
        "--chalk",
        "--muted",
        "--maroon",
        "--verified-teal",
        "--signal-amber",
        "--ember-orange",
        "--hazard-red",
    ):
        assert token in css
    for alias in ("--space-xs", "--space-sm", "--space-md", "--space-lg", "--space-xl"):
        assert alias in tokens
    assert "#" not in css
    assert "#1c2024" not in css.lower()


def test_document_title_set_for_authenticated_shell():
    shell = (SHELL / "Shell.tsx").read_text(encoding="utf-8")
    assert "SentinelLoop AI Dashboard" in shell
