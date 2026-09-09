import os
import uuid
import tempfile
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Response, status
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from airstore.core.config import settings
from airstore.core.models import (
    NodeRegistrationRequest, NodeRegistrationResponse, HeartbeatRequest, HeartbeatResponse,
    NodeModel, FileModel, FileDetailResponse, NodeStatus, EventType, EventModel
)
from airstore.manager.database.db import DatabaseManager
from airstore.manager.placement import RuleBasedPlacementStrategy
from airstore.manager.services.storage_manager import StorageManagerService
from airstore.manager.services.recovery_service import RecoveryService
from airstore.manager.scheduler.heartbeat_monitor import HeartbeatMonitor

logger = logging.getLogger("airstore.manager")

def create_manager_app(db_path: Optional[Path] = None, start_monitor: bool = True) -> FastAPI:
    database_path = db_path or settings.MANAGER_DB_PATH
    db = DatabaseManager(database_path)
    recovery_service = RecoveryService(db)
    storage_service = StorageManagerService(db, placement_strategy=RuleBasedPlacementStrategy())
    heartbeat_monitor = HeartbeatMonitor(db, recovery_service, check_interval=2.0)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_monitor:
            heartbeat_monitor.start()
        yield
        if start_monitor:
            heartbeat_monitor.stop()

    app = FastAPI(
        title="AirStore Manager Node API",
        description="AirStore Offline Distributed Storage Controller",
        version="0.1.0",
        lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.db = db
    app.state.storage_service = storage_service
    app.state.recovery_service = recovery_service
    app.state.heartbeat_monitor = heartbeat_monitor

    # --- Node Endpoints ---

    @app.post("/api/nodes/{node_id}/recover")
    def trigger_node_recovery(node_id: str):
        node = db.get_node(node_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node {node_id} not found.")
        result = recovery_service.recover_node_failure(node_id)
        return result

    @app.post("/api/nodes/register", response_model=NodeRegistrationResponse)
    def register_node(req: NodeRegistrationRequest):
        if req.auth_secret != settings.AUTH_SECRET:
            raise HTTPException(status_code=403, detail="Invalid cluster authorization secret.")

        node = NodeModel(
            node_id=req.node_id,
            hostname=req.hostname,
            ip=req.ip,
            port=req.port,
            total_storage=req.total_storage,
            available_storage=req.available_storage,
            status=NodeStatus.ONLINE,
            last_heartbeat=datetime.now(timezone.utc)
        )
        db.register_or_update_node(node)

        # Log event
        event = EventModel(
            event_id=str(uuid.uuid4()),
            event_type=EventType.NODE_JOINED,
            message=f"Node '{req.node_id}' ({req.ip}:{req.port}) joined the network.",
            details={"node_id": req.node_id, "ip": req.ip, "port": req.port}
        )
        db.add_event(event)

        return NodeRegistrationResponse(
            success=True,
            node_id=req.node_id,
            message=f"Node {req.node_id} successfully registered.",
            config={"chunk_size": settings.CHUNK_SIZE, "heartbeat_interval": settings.HEARTBEAT_INTERVAL}
        )

    @app.post("/api/nodes/heartbeat", response_model=HeartbeatResponse)
    def handle_heartbeat(req: HeartbeatRequest):
        success = db.update_node_heartbeat(
            node_id=req.node_id,
            available_storage=req.available_storage,
            total_storage=req.total_storage,
            status=req.status
        )
        if not success:
            raise HTTPException(status_code=444, detail=f"Node {req.node_id} not registered.")
        
        return HeartbeatResponse(
            acknowledged=True,
            timestamp=datetime.now(timezone.utc),
            commands=[]
        )

    @app.get("/api/nodes", response_model=List[NodeModel])
    def list_nodes():
        return db.list_nodes()

    # --- File Endpoints ---

    @app.get("/api/files", response_model=List[FileModel])
    def list_files():
        return db.list_files()

    @app.get("/api/files/{file_id}", response_model=FileDetailResponse)
    def get_file_details(file_id: str):
        file_model = db.get_file(file_id)
        if not file_model:
            raise HTTPException(status_code=404, detail="File not found")

        chunks = db.get_chunks_for_file(file_id)
        replicas = db.get_all_replicas_for_file(file_id)
        nodes = {n.node_id: n for n in db.list_nodes()}

        return FileDetailResponse(
            file=file_model,
            chunks=chunks,
            replicas=replicas,
            nodes=nodes
        )

    @app.post("/api/files/upload", response_model=FileModel)
    async def upload_file(
        file: UploadFile = File(...),
        chunk_size: int = Form(settings.CHUNK_SIZE),
        replication_factor: int = Form(settings.REPLICATION_FACTOR)
    ):
        # Save temp file
        temp_dir = Path(tempfile.gettempdir()) / "airstore_uploads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_filepath = temp_dir / f"{uuid.uuid4()}_{file.filename}"

        try:
            with open(temp_filepath, "wb") as f:
                while content := await file.read(1024 * 1024):
                    f.write(content)

            uploaded_file = storage_service.process_file_upload(
                source_file_path=temp_filepath,
                filename=file.filename,
                chunk_size=chunk_size,
                replication_factor=replication_factor
            )
            return uploaded_file
        finally:
            if temp_filepath.exists():
                os.remove(temp_filepath)

    @app.get("/api/files/{file_id}/download")
    def download_file(file_id: str):
        file_model = db.get_file(file_id)
        if not file_model:
            raise HTTPException(status_code=404, detail="File not found")

        temp_dir = Path(tempfile.gettempdir()) / "airstore_downloads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_output = temp_dir / f"dl_{file_id}_{file_model.filename}"

        try:
            storage_service.stream_file_reconstruction(file_id, temp_output)
            return FileResponse(
                path=temp_output,
                filename=file_model.filename,
                media_type="application/octet-stream"
            )
        except Exception as e:
            logger.error(f"Download reconstruction failed for file {file_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/files/{file_id}")
    def delete_file(file_id: str):
        deleted = storage_service.delete_file(file_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="File not found")
        return {"status": "success", "file_id": file_id}

    # --- System Stats & Logs ---

    @app.get("/api/stats")
    def get_system_stats():
        nodes = db.list_nodes()
        files = db.list_files()
        
        online_nodes = [n for n in nodes if n.status == NodeStatus.ONLINE]
        offline_nodes = [n for n in nodes if n.status == NodeStatus.OFFLINE]

        total_cap = sum(n.total_storage for n in online_nodes)
        avail_cap = sum(n.available_storage for n in online_nodes)
        used_cap = total_cap - avail_cap

        return {
            "total_storage": total_cap,
            "available_storage": avail_cap,
            "used_storage": used_cap,
            "total_nodes": len(nodes),
            "online_nodes": len(online_nodes),
            "offline_nodes": len(offline_nodes),
            "total_files": len(files),
            "replication_factor": settings.REPLICATION_FACTOR
        }

    @app.get("/api/events")
    def get_events(limit: int = Query(50)):
        return db.list_events(limit=limit)

    @app.get("/api/transfers")
    def get_transfers(limit: int = Query(50)):
        return db.list_transfers(limit=limit)

    # Mount static frontend files if directory exists
    frontend_dir = Path(__file__).parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    return app
