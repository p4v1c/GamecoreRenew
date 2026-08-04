"""The pack catalogue — one emulator or application per directory.

See `loader.py` for the merge rule (local wins) and the data-only rule that
applies to `config/catalog.d/`.
"""
from .loader import (
    CATALOG_DIR,
    LOCAL_DIR,
    PRIVILEGED_BLOCKS,
    PRIVILEGED_FILES,
    SCHEMA_FILE,
    Pack,
    load_catalog,
)
from .schema import SchemaError, load_schema, validate

__all__ = [
    "CATALOG_DIR", "LOCAL_DIR", "SCHEMA_FILE",
    "PRIVILEGED_BLOCKS", "PRIVILEGED_FILES",
    "Pack", "load_catalog",
    "SchemaError", "load_schema", "validate",
]
