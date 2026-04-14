import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from server.routes.simulation import SimulationManager

@pytest.fixture
def mock_poller():
    poller = MagicMock()
    poller.start = AsyncMock()
    poller.stop = AsyncMock()
    poller.is_running = False
    return poller

@pytest.fixture
def mock_ws_manager():
    ws = MagicMock()
    ws.broadcast = AsyncMock()
    return ws

@pytest.mark.asyncio
async def test_start_simulation(mock_poller, mock_ws_manager):
    mgr = SimulationManager(timeout_seconds=600)
    await mgr.start(mock_poller, mock_ws_manager)
    assert mgr.is_running is True
    mock_poller.start.assert_called_once()

@pytest.mark.asyncio
async def test_stop_simulation(mock_poller, mock_ws_manager):
    mgr = SimulationManager(timeout_seconds=600)
    await mgr.start(mock_poller, mock_ws_manager)
    await mgr.stop(mock_poller, mock_ws_manager)
    assert mgr.is_running is False
    mock_poller.stop.assert_called_once()

@pytest.mark.asyncio
async def test_auto_shutdown(mock_poller, mock_ws_manager):
    mgr = SimulationManager(timeout_seconds=1)
    await mgr.start(mock_poller, mock_ws_manager)
    assert mgr.is_running is True
    await asyncio.sleep(1.5)
    assert mgr.is_running is False
    mock_ws_manager.broadcast.assert_called()

@pytest.mark.asyncio
async def test_remaining_seconds(mock_poller, mock_ws_manager):
    mgr = SimulationManager(timeout_seconds=600)
    assert mgr.remaining_seconds == 0
    await mgr.start(mock_poller, mock_ws_manager)
    remaining = mgr.remaining_seconds
    assert 595 < remaining <= 600
    await mgr.stop(mock_poller, mock_ws_manager)
