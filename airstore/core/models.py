from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class NodeStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    RECOVERING = "RECOVERING"
    DEGRADED = "DEGRADED"

class FileStatus(str, Enum):
    UPLOADING = "UPLOADING"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    CORRUPTED = "CORRUPTED"
    DELETED = "DELETED"

class ReplicaStatus(str, Enum):
    STORED = "STORED"
    MISSING = "MISSING"
    CORRUPTED = "CORRUPTED"
    PENDING = "PENDING"

class TransferType(str, Enum):
    UPLOAD = "UPLOAD"
    DOWNLOAD = "DOWNLOAD"

class TransferStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class EventType(str, Enum):
    NODE_JOINED = "NODE_JOINED"
    NODE_OFFLINE = "NODE_OFFLINE"
    NODE_HEALTHY = "NODE_HEALTHY"
    FILE_UPLOADED = "FILE_UPLOADED"
    FILE_DOWNLOADED = "FILE_DOWNLOADED"
    FILE_DELETED = "FILE_DELETED"
    CHUNK_CREATED = "CHUNK_CREATED"
    CHUNK_REPLICATED = "CHUNK_REPLICATED"
    CHUNK_VERIFIED = "CHUNK_VERIFIED"
    CHUNK_CORRUPTED = "CHUNK_CORRUPTED"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
    RECOVERY_FAILED = "RECOVERY_FAILED"

# Database & API Data Models

class NodeModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: str
    hostname: str
    ip: str
    port: int
    total_storage: int  # bytes
    available_storage: int  # bytes
    status: NodeStatus = NodeStatus.ONLINE
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class FileModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_id: str
    filename: str
    size: int  # bytes
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    overall_hash: str
    status: FileStatus = FileStatus.ACTIVE
    chunk_size: int = 64 * 1024 * 1024
    replication_factor: int = 2
    encrypted: bool = False

class ChunkModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: str
    file_id: str
    sequence_number: int
    size: int  # unencrypted chunk bytes
    sha256: str  # sha256 of unencrypted chunk data

class ChunkReplicaModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: str
    node_id: str
    replica_number: int
    status: ReplicaStatus = ReplicaStatus.STORED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TransferModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transfer_id: str
    file_id: str
    transfer_type: TransferType
    status: TransferStatus = TransferStatus.IN_PROGRESS
    progress: float = 0.0  # 0 to 100
    speed_mbps: float = 0.0
    error_message: Optional[str] = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

class EventModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    event_type: EventType
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Request / Response Schemas

class NodeRegistrationRequest(BaseModel):
    node_id: str
    hostname: str
    ip: str
    port: int
    total_storage: int
    available_storage: int
    auth_secret: str

class NodeRegistrationResponse(BaseModel):
    success: bool
    node_id: str
    message: str
    config: Dict[str, Any] = {}

class HeartbeatRequest(BaseModel):
    node_id: str
    available_storage: int
    total_storage: int
    status: NodeStatus = NodeStatus.ONLINE

class HeartbeatResponse(BaseModel):
    acknowledged: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    commands: List[Dict[str, Any]] = []

class FileDetailResponse(BaseModel):
    file: FileModel
    chunks: List[ChunkModel]
    replicas: List[ChunkReplicaModel]
    nodes: Dict[str, NodeModel]

class ChunkLocationInfo(BaseModel):
    chunk_id: str
    sequence_number: int
    size: int
    sha256: str
    nodes: List[NodeModel]
