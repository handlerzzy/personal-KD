"""Shared test fixtures and configuration."""

import pytest


@pytest.fixture(autouse=True)
def _clear_rate_limit_store():
    """Clear the in-memory rate limit store before each test.

    The rate limiter in app.main uses a module-level dict that persists
    across tests, causing auth_headers fixture to hit 429 after ~5 tests.
    """
    from app.main import _rate_limit_store

    _rate_limit_store.clear()
    yield
    _rate_limit_store.clear()
