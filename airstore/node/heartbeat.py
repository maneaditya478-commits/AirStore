import asyncio
import httpx
import logging
from typing import Optional, Callable
from airstore.core.models import HeartbeatRequest, HeartbeatResponse, NodeStatus
from airstore.core.config import settings

logger = logging.getLogger("airstore.node.heartbeat")

class HeartbeatSender:
    """Sends periodic heartbeats to the Manager Node."""

    def __init__(
        self,
        manager_url: str,
        node_id: str,
        stats_provider: Callable[[], dict],
        interval: float = settings.HEARTBEAT_INTERVAL
    ):
        self.manager_url = manager_url.rstrip("/")
        self.node_id = node_id
        self.stats_provider = stats_provider
        self.interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def send_heartbeat_once(self) -> Optional[HeartbeatResponse]:
        """Send a single heartbeat request."""
        stats = self.stats_provider()
        payload = HeartbeatRequest(
            node_id=self.node_id,
            available_storage=stats.get("available_storage", 0),
            total_storage=stats.get("total_storage", 0),
            status=NodeStatus.ONLINE
        )
        url = f"{self.manager_url}/api/nodes/heartbeat"

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.post(url, json=payload.model_dump())
                if resp.status_code == 200:
                    data = resp.json()
                    return HeartbeatResponse(**data)
                else:
                    logger.warning(f"Heartbeat rejected by manager status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.debug(f"Heartbeat send failed for node {self.node_id}: {e}")
        return None

    async def _loop(self):
        while self._running:
            try:
                await self.send_heartbeat_once()
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
            await asyncio.sleep(self.interval)

    def start(self):
        """Start the background heartbeat loop."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())
            logger.info(f"Heartbeat sender started for node {self.node_id} every {self.interval}s")

    def stop(self):
        """Stop the background heartbeat loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info(f"Heartbeat sender stopped for node {self.node_id}")
