from __future__ import annotations

import pytest

from core.settings import Settings


def test_settings_does_not_read_env_at_class_definition() -> None:
    with pytest.raises(TypeError):
        Settings()
