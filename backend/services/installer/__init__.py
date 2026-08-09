"""Obtaining the binaries a pack declares.

A provider is a strategy, not a pack: `flatpak.py` serves eleven packs and
belongs to none of them. That is why this lives in backend/services/ and not
inside catalog/<id>/.
"""
from . import manifest
from .applier import (
    AppContext,
    apply,
    apply_files,
    apply_packages,
    apply_services,
    apply_sources,
    apply_udev,
    enabled_units,
    run_post_install,
)
from .fetch import (
    FetchError,
    download,
    extract,
    fetch_release_asset,
    github_api_asset,
    github_asset_url,
    sha256_of,
)
from .providers import PROVIDERS, Context, Result, install, sandbox_flags

__all__ = [
    "AppContext", "apply", "apply_files", "apply_packages", "apply_services",
    "apply_udev",
    "apply_sources", "enabled_units", "run_post_install",
    "Context", "Result", "PROVIDERS", "install", "sandbox_flags",
    "download", "extract", "fetch_release_asset", "github_asset_url",
    "github_api_asset", "sha256_of", "FetchError", "manifest",
]
