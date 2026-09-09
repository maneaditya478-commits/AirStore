import httpx
import logging
from typing import Dict, Any, Optional
from airstore.core.models import NodeRegistrationRequest, NodeRegistrationResponse
from airstore.core.config import settings

logger = logging.getLogger("airstore.node.registration")

class NodeRegister:
    """Handles Storage Node registration with Manager Node."""

    def __init__(self, manager_url: str, node_id: str, hostname: str, ip: str, port: int):
        self.manager_url = manager_url.rstrip("/")
        self.node_id = node_id
        self.hostname = hostname
        self.ip = ip
        self.port = port

    def register(self, total_storage: int, available_storage: int) -> NodeRegistrationResponse:
        """Send registration request to Manager REST API."""
        url = f"{self.manager_url}/api/nodes/register"
        payload = NodeRegistrationRequest(
            node_id=self.node_id,
            hostname=self.hostname,
            ip=self.ip,
            port=self.port,
            total_storage=total_storage,
            available_storage=available_storage,
            auth_secret=settings.AUTH_SECRET
        )

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(url, json=payload.model_dump())
                resp.raise_for_status()
                data = resp.json()
                return NodeRegistrationResponse(**data)
        except Exception as e:
            logger.error(f"Failed to register node {self.node_id} with manager at {url}: {e}")
            return NodeRegistrationResponse(
                success=False,
                node_id=self.node_id,
                message=f"Registration request failed: {str(e)}"
            )
