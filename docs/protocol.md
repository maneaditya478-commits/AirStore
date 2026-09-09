# AirStore Communication Protocol Specification

All node-to-manager and node-to-node communication occurs over local network HTTP/REST interfaces.

## 1. Node Registration Protocol
- **Endpoint**: `POST /api/nodes/register`
- **Request**:
  ```json
  {
    "node_id": "node_01",
    "hostname": "node-host",
    "ip": "192.168.1.50",
    "port": 8001,
    "total_storage": 1073741824000,
    "available_storage": 536870912000,
    "auth_secret": "airstore-secret-cluster-auth-key"
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "node_id": "node_01",
    "message": "Node node_01 successfully registered.",
    "config": { "chunk_size": 67108864, "heartbeat_interval": 5.0 }
  }
  ```

## 2. Heartbeat Protocol
- **Endpoint**: `POST /api/nodes/heartbeat`
- **Interval**: Configurable (default 5.0 seconds).
- **Timeout**: 15.0 seconds before marking node `OFFLINE`.

## 3. Storage Node Chunk Endpoints
- `PUT /chunks/{chunk_id}`: Stream chunk payload into node disk.
- `GET /chunks/{chunk_id}`: Stream raw chunk bytes back to requester.
- `DELETE /chunks/{chunk_id}`: Delete chunk file.
- `GET /chunks/{chunk_id}/verify?sha256={hash}`: Verify local chunk integrity.
- `POST /replicate`: Instruct node to copy chunk from source node (`{ "chunk_id", "source_node_url", "sha256" }`).
