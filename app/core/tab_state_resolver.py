from __future__ import annotations

from app.config.constants import DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME


def merge_tabs_state(
    *,
    history_tabs: list[dict[str, object]],
    history_active_tab: str,
    settings_tab_order: list[str],
    settings_active_tab: str | None,
    settings_user_tabs: list[dict[str, object]] | None = None,
    default_tab_name: str = DEFAULT_CLIP_TAB_NAME,
    image_tab_name: str = DEFAULT_IMAGE_TAB_NAME,
) -> tuple[list[dict[str, object]], str]:
    normalized_history = _normalize_history_tabs(history_tabs)

    buffer_tab = _take_or_create_system_tab(
        normalized_history=normalized_history,
        target_name=default_tab_name,
    )
    image_tab = _take_or_create_system_tab(
        normalized_history=normalized_history,
        target_name=image_tab_name,
    )

    history_user_tabs: list[dict[str, object]] = [
        tab
        for tab in normalized_history
        if not _is_system_tab(
            name=str(tab.get("name", "")),
            default_tab_name=default_tab_name,
            image_tab_name=image_tab_name,
        )
    ]
    source_user_tabs = (
        _normalize_history_tabs(settings_user_tabs)
        if settings_user_tabs is not None
        else history_user_tabs
    )
    source_user_tabs = [
        tab
        for tab in source_user_tabs
        if not _is_system_tab(
            name=str(tab.get("name", "")),
            default_tab_name=default_tab_name,
            image_tab_name=image_tab_name,
        )
    ]
    remaining_by_casefold = {
        str(tab["name"]).casefold(): tab for tab in source_user_tabs if isinstance(tab.get("name"), str)
    }
    user_tab_order = [str(tab["name"]).casefold() for tab in source_user_tabs]

    resolved_user_tabs: list[dict[str, object]] = []
    for tab_name in _normalize_tab_order(settings_tab_order):
        if _is_system_tab(
            name=tab_name,
            default_tab_name=default_tab_name,
            image_tab_name=image_tab_name,
        ):
            continue

        casefold_name = tab_name.casefold()
        existing_tab = remaining_by_casefold.pop(casefold_name, None)
        if existing_tab is not None:
            resolved_user_tabs.append(existing_tab)
            continue
        resolved_user_tabs.append(_empty_tab(tab_name))

    for casefold_name in user_tab_order:
        leftover = remaining_by_casefold.pop(casefold_name, None)
        if leftover is not None:
            resolved_user_tabs.append(leftover)

    resolved_tabs = [buffer_tab, image_tab, *resolved_user_tabs]
    resolved_active_tab = _resolve_active_tab(
        tabs=resolved_tabs,
        settings_active_tab=settings_active_tab,
        history_active_tab=history_active_tab,
    )
    return resolved_tabs, resolved_active_tab


def _normalize_history_tabs(history_tabs: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized_tabs: list[dict[str, object]] = []
    seen_tabs: set[str] = set()

    for raw_tab in history_tabs:
        if not isinstance(raw_tab, dict):
            continue
        name = _normalize_tab_name(raw_tab.get("name"))
        if name is None:
            continue
        casefold_name = name.casefold()
        if casefold_name in seen_tabs:
            continue
        seen_tabs.add(casefold_name)
        normalized_tabs.append(
            {
                "name": name,
                "capture_locked": bool(raw_tab.get("capture_locked", False)),
                "items": raw_tab.get("items") if isinstance(raw_tab.get("items"), list) else [],
            }
        )
    return normalized_tabs


def _normalize_tab_order(tab_order: list[str]) -> list[str]:
    normalized_order: list[str] = []
    seen: set[str] = set()
    for raw_name in tab_order:
        name = _normalize_tab_name(raw_name)
        if name is None:
            continue
        casefold_name = name.casefold()
        if casefold_name in seen:
            continue
        seen.add(casefold_name)
        normalized_order.append(name)
    return normalized_order


def _take_or_create_system_tab(
    *,
    normalized_history: list[dict[str, object]],
    target_name: str,
) -> dict[str, object]:
    target_key = target_name.casefold()
    for tab in normalized_history:
        name = str(tab.get("name", ""))
        if name.casefold() != target_key:
            continue
        return {
            "name": target_name,
            "capture_locked": False,
            "items": tab.get("items") if isinstance(tab.get("items"), list) else [],
        }
    return _empty_tab(target_name)


def _resolve_active_tab(
    *,
    tabs: list[dict[str, object]],
    settings_active_tab: str | None,
    history_active_tab: str,
) -> str:
    resolved_from_settings = _resolve_tab_name(
        tabs=tabs,
        target=settings_active_tab,
    )
    if resolved_from_settings is not None:
        return resolved_from_settings

    resolved_from_history = _resolve_tab_name(
        tabs=tabs,
        target=history_active_tab,
    )
    if resolved_from_history is not None:
        return resolved_from_history

    if tabs:
        return str(tabs[0].get("name", DEFAULT_CLIP_TAB_NAME))
    return DEFAULT_CLIP_TAB_NAME


def _resolve_tab_name(*, tabs: list[dict[str, object]], target: str | None) -> str | None:
    normalized_target = _normalize_tab_name(target)
    if normalized_target is None:
        return None

    target_key = normalized_target.casefold()
    for tab in tabs:
        name = _normalize_tab_name(tab.get("name"))
        if name is None:
            continue
        if name.casefold() == target_key:
            return name
    return None


def _normalize_tab_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


def _is_system_tab(*, name: str, default_tab_name: str, image_tab_name: str) -> bool:
    casefold_name = name.casefold()
    return casefold_name in {default_tab_name.casefold(), image_tab_name.casefold()}


def _empty_tab(name: str) -> dict[str, object]:
    return {
        "name": name,
        "capture_locked": False,
        "items": [],
    }
