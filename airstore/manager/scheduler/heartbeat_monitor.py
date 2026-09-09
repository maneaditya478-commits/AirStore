import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from airstore.core.config import settings
from airstore.core.models import NodeStatus
from airstore.manager.database.db import DatabaseManager
from airstore.manager.services.recovery_service import RecoveryService

logger = logging.getLogger("airstore.manager.heartbeat_monitor")

class HeartbeatMonitor:
    """
    Monitors node heartbeats and triggers fault recovery when a node misses heartbeats.
    """

    def __init__(
        self,
        db: DatabaseManager,
        recovery_service: RecoveryService,
        check_interval: float = 3.0,
        timeout_seconds: float = settings.HEARTBEAT_TIMEOUT
    ):
        self.db = db
        self.recovery_service = recovery_service
        self.check_interval = check_interval
        self.timeout_seconds = timeout_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def check_nodes_now(self):
        """Inspect all nodes and trigger recovery for timed out nodes."""
        now = datetime.now(timezone.utc)
        nodes = self.db.list_nodes()

        for node in nodes:
            if node.status != NodeStatus.ONLINE:
                continue

            last_hb = node.last_heartbeat
            if last_hb.tzinfo is None:
                last_hb = last_hb.replace(tzinfo=timezone.utc)

            elapsed = (now - last_hb).total_seconds()
            if elapsed > self.timeout_seconds:
                logger.warning(f"Node '{node.node_id}' missed heartbeats for {elapsed:.1f}s (timeout: {self.timeout_seconds}s). Marking OFFLINE!")
                self.recovery_service.recover_node_failure(node.node_id)

    async def _monitor_loop(self):
        while self._running:
            try:
                self.check_nodes_now()
            except Exception as e:
                logger.error(f"Error in heartbeat monitor loop: {e}")
            await asyncio.sleep(self.check_interval)

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._monitor_loop())
            logger.info(f"Heartbeat monitor started (timeout: {self.timeout_seconds}s, interval: {self.check_interval}s)")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Heartbeat monitor stopped.")
