from .base import AdapterHealth, SourceAdapter
from .rss import RssAdapter
from .html import HtmlAdapter
from .browser import BrowserAdapter
from .mail import MailAdapter

ADAPTERS_BY_METHOD = {
    "rss": RssAdapter,
    "html": HtmlAdapter,
    "browser": BrowserAdapter,
    "mail": MailAdapter,
}

__all__ = [
    "AdapterHealth",
    "SourceAdapter",
    "RssAdapter",
    "HtmlAdapter",
    "BrowserAdapter",
    "MailAdapter",
    "ADAPTERS_BY_METHOD",
]
