"""Fixtures for exercising Liquipedia API calls offline."""

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest


@pytest.fixture
def mock_liquipedia_session():
    """Build an aiohttp session whose response comes from a test."""

    def make_session(read_json: AsyncMock) -> MagicMock:
        session = MagicMock(spec=aiohttp.ClientSession)
        response = MagicMock(spec=aiohttp.ClientResponse, status=200, json=read_json)
        session.get.return_value.__aenter__ = AsyncMock(return_value=response)
        session.get.return_value.__aexit__ = AsyncMock(return_value=False)
        return session

    return make_session
