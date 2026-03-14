"""Test configuration and fixtures."""

import pytest


@pytest.fixture
def anyio_backend():
    """Use asyncio for all async tests."""
    return "asyncio"
