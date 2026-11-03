"""MemHub Core."""

import os

from one_memory.hy_runtime_config import configure_hy_behavior_environment

# HY has a few reader switches evaluated at module import time.  Fix the
# product-owned, non-secret behavior before any one_memory module imports HY.
configure_hy_behavior_environment()

_version = os.environ.get("ONE_MEMORY_VERSION", "").strip()
__version__ = _version if _version else "development"
