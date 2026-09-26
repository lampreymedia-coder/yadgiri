"""Read-only check of the Bale_Archive database, in plain Persian.

    python scripts/preflight.py

Exit code 0 = everything is ready; 1 = something must be fixed by the owner
(the exact command is printed). This script never changes the database.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.preflight import format_report, run_preflight


def main() -> int:
    settings = get_settings()
    checks = asyncio.run(run_preflight(settings.database_url))
    print(format_report(checks))
    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
