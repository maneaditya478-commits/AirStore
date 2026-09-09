import os
import secrets
from pathlib import Path
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Cluster configuration
    CHUNK_SIZE: int = Field(default=64 * 1024 * 1024, description="Default chunk size in bytes (64MB)")
    REPLICATION_FACTOR: int = Field(default=2, description="Default replica count per chunk")
    HEARTBEAT_INTERVAL: float = Field(default=5.0, description="Heartbeat interval in seconds")
    HEARTBEAT_TIMEOUT: float = Field(default=15.0, description="Timeout in seconds before marking a node OFFLINE")
    
    # Manager & Node Defaults
    MANAGER_HOST: str = Field(default="127.0.0.1")
    MANAGER_PORT: int = Field(default=8000)
    NODE_HOST: str = Field(default="127.0.0.1")
    NODE_PORT: int = Field(default=8001)
    
    # Storage Paths
    BASE_DIR: Path = Path(os.getcwd())
    DATA_DIR: Path = Path(os.getcwd()) / "data"
    MANAGER_DB_PATH: Path = Path(os.getcwd()) / "data" / "manager.db"
    NODE_STORAGE_DIR: Path = Path(os.getcwd()) / "data" / "node_storage"
    
    # Security
    ENCRYPTION_ENABLED: bool = Field(default=False, description="Enable AES-GCM chunk encryption")
    # Default 32-byte (256-bit) key for testing/dev, override in env via AIRSTORE_ENCRYPTION_KEY
    ENCRYPTION_KEY_HEX: str = Field(
        default="000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
        description="Hex string of 32-byte encryption key"
    )
    AUTH_SECRET: str = Field(default="airstore-secret-cluster-auth-key", description="Shared secret for node registration")
    
    @property
    def encryption_key(self) -> bytes:
        return bytes.fromhex(self.ENCRYPTION_KEY_HEX)

    model_config = ConfigDict(env_prefix="AIRSTORE_")

settings = Settings()
