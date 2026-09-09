import os
import socket
import logging
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Query, Header, status
from fastapi.responses import Response, StreamingResponse
import httpx

from airstore.core.config import settings, get_lan_ip
from airstore.core.models import NodeStatus
from airstore.node.storage import StorageEngine
from airstore.node.registration import NodeRegister
from airstore.node.heartbeat import HeartbeatSender

logger = logging.getLogger("airstore.node")

def create_node_app(
    node_id: str,
    storage_dir: Path,
    manager_url: str = f"http://{settings.MANAGER_HOST}:{settings.MANAGER_PORT}",
    host: str = "127.0.0.1",
    port: int = 8001,
    auto_register: bool = True
) -> FastAPI:
    
    storage_engine = StorageEngine(storage_dir)
    hostname = socket.gethostname()
    
    # Resolve advertised IP for LAN registration
    advertised_ip = settings.ADVERTISED_IP
    if not advertised_ip:
        if host in ("0.0.0.0", "::"):
            advertised_ip = get_lan_ip()
        else:
            advertised_ip = host
    
    heartbeat_sender = HeartbeatSender(
        manager_url=manager_url,
        node_id=node_id,
        stats_provider=storage_engine.get_stats
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        if auto_register:
            stats = storage_engine.get_stats()
            registrar = NodeRegister(manager_url, node_id, hostname, advertised_ip, port)
            res = registrar.register(stats["total_storage"], stats["available_storage"])
            if res.success:
                logger.info(f"Storage node {node_id} successfully registered with manager.")
            else:
                logger.warning(f"Storage node {node_id} registration warning: {res.message}")
        
        heartbeat_sender.start()
        yield
        # Shutdown
        heartbeat_sender.stop()

    app = FastAPI(
        title=f"AirStore Storage Node {node_id}",
        description="AirStore local storage node API",
        version="0.1.0",
        lifespan=lifespan
    )
    
    app.state.node_id = node_id
    app.state.storage_engine = storage_engine
    app.state.manager_url = manager_url
    app.state.host = host
    app.state.port = port

    @app.get("/health")
    def health():
        stats = storage_engine.get_stats()
        return {
            "node_id": node_id,
            "status": NodeStatus.ONLINE,
            "hostname": hostname,
            "ip": host,
            "port": port,
            "stats": stats
        }

    @app.put("/chunks/{chunk_id}")
    async def store_chunk(
        chunk_id: str,
        request: Request,
        sha256: Optional[str] = Query(None)
    ):
        if ".." in chunk_id or "/" in chunk_id or "\\" in chunk_id:
            raise HTTPException(status_code=400, detail="Invalid chunk ID: Path traversal attempt detected.")
        try:
            body = await request.body()
            stored_bytes = storage_engine.store_chunk(chunk_id, body, expected_sha256=sha256)
            return {
                "status": "success",
                "chunk_id": chunk_id,
                "bytes_stored": stored_bytes,
                "node_id": node_id
            }
        except Exception as e:
            logger.error(f"Error storing chunk {chunk_id}: {e}")
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/chunks/{chunk_id}")
    def get_chunk(chunk_id: str):
        if ".." in chunk_id or "/" in chunk_id or "\\" in chunk_id:
            raise HTTPException(status_code=400, detail="Invalid chunk ID: Path traversal attempt detected.")
        try:
            data = storage_engine.retrieve_chunk(chunk_id)
            return Response(content=data, media_type="application/octet-stream")
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} not found on node {node_id}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/chunks/{chunk_id}")
    def delete_chunk(chunk_id: str):
        deleted = storage_engine.delete_chunk(chunk_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} not found on node {node_id}")
        return {"status": "success", "chunk_id": chunk_id, "node_id": node_id}

    @app.get("/chunks/{chunk_id}/verify")
    def verify_chunk(chunk_id: str, sha256: str = Query(...)):
        valid = storage_engine.verify_chunk(chunk_id, sha256)
        return {
            "chunk_id": chunk_id,
            "valid": valid,
            "node_id": node_id
        }

    @app.post("/replicate")
    async def replicate_chunk(request_data: dict):
        """
        Instruction from Manager to copy a chunk from source_node_url to this node.
        Payload: { "chunk_id": str, "source_node_url": str, "sha256": str }
        """
        chunk_id = request_data.get("chunk_id")
        source_node_url = request_data.get("source_node_url")
        expected_sha256 = request_data.get("sha256")

        if not chunk_id or not source_node_url:
            raise HTTPException(status_code=400, detail="Missing chunk_id or source_node_url")

        source_url = f"{source_node_url.rstrip('/')}/chunks/{chunk_id}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(source_url)
                resp.raise_for_status()
                chunk_data = resp.content

            storage_engine.store_chunk(chunk_id, chunk_data, expected_sha256=expected_sha256)
            return {
                "status": "success",
                "chunk_id": chunk_id,
                "replicated_to": node_id,
                "bytes": len(chunk_data)
            }
        except Exception as e:
            logger.error(f"Replication of {chunk_id} failed from {source_url}: {e}")
            raise HTTPException(status_code=500, detail=f"Replication failed: {str(e)}")

    return app
