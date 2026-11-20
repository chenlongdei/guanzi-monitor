import os

from .base import PLATFORMS, Page, Provider, ProviderError  # noqa: F401


def get_provider(settings: dict, on_call=None, name: str | None = None) -> Provider:
    if os.environ.get("DEI_WB_DEMO"):
        from .demo import DemoProvider
        return DemoProvider(settings, on_call)
    name = name or settings.get("provider") or "monid"
    if name == "tikhub":
        from .tikhub import TikHubProvider
        return TikHubProvider(settings, on_call)
    from .monid import MonidProvider
    return MonidProvider(settings, on_call)
