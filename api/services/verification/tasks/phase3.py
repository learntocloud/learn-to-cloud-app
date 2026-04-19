"""Phase 3 constants.

Contains the shared ``MAX_FILE_SIZE_BYTES`` constant used by
PR diff verification.
"""

from __future__ import annotations

# Maximum file size to prevent token exhaustion (50KB)
MAX_FILE_SIZE_BYTES: int = 50 * 1024
