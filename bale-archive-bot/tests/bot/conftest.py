from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from tests.bot.harness import Harness, make_settings
from tests.conftest import RootDB


@pytest.fixture
async def h(db: RootDB, api: Any, fake_bale: Any, tmp_path: Path) -> AsyncIterator[Harness]:
    harness = Harness(make_settings(tmp_path), api, fake_bale, db)
    yield harness
    await harness.close()
