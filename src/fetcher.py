"""Placeholder fetcher/parser module for future SEC 13F ingestion."""

from __future__ import annotations

import requests
import pandas as pd
from lxml import etree


def health_check_dependencies() -> dict[str, str]:
    """Simple function proving requests/pandas/lxml are wired in MVP."""
    return {
        "requests": requests.__version__,
        "pandas": pd.__version__,
        "lxml": etree.LXML_VERSION.__str__(),
    }
