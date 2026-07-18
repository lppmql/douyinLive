import unittest
from unittest.mock import AsyncMock, patch

from app.services.asr.websocket_manager import WebSocketManager


class RunningTask:
    def done(self):
        return False


class WebSocketManagerTest(unittest.IsolatedAsyncioTestCase):
    async def test_multiple_session_connections_share_one_redis_listener(self):
        manager = WebSocketManager()

        async def start_listener():
            manager._pubsub_task = RunningTask()

        with patch.object(manager, "_start_listener", new=AsyncMock(side_effect=start_listener)) as start:
            await manager.connect(101, AsyncMock())
            await manager.connect(102, AsyncMock())

        self.assertEqual(start.await_count, 1)
        self.assertEqual(set(manager._connections), {101, 102})


if __name__ == "__main__":
    unittest.main()
