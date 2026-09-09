from abc import ABC, abstractmethod
from typing import List, Optional
from airstore.core.models import ChunkModel, NodeModel, NodeStatus

class PlacementError(Exception):
    """Exception raised when chunk replica placement fails."""
    pass

class InsufficientNodesError(PlacementError):
    """Raised when not enough healthy storage nodes are available to meet replication requirements."""
    pass

class PlacementStrategy(ABC):
    """Abstract base class for chunk replica placement algorithms."""

    @abstractmethod
    def select_nodes_for_chunk(
        self,
        chunk: ChunkModel,
        available_nodes: List[NodeModel],
        replication_factor: int,
        existing_replica_node_ids: Optional[List[str]] = None
    ) -> List[NodeModel]:
        """
        Select target nodes for storing replicas of a chunk.
        """
        pass

class RuleBasedPlacementStrategy(PlacementStrategy):
    """
    Deterministic rule-based placement strategy.
    
    Rules:
    1. Only select ONLINE nodes.
    2. Exclude nodes already storing a replica of this chunk.
    3. Exclude nodes with insufficient available storage for chunk.size.
    4. Balance storage load by sorting candidate nodes by available_storage (descending).
    """

    def select_nodes_for_chunk(
        self,
        chunk: ChunkModel,
        available_nodes: List[NodeModel],
        replication_factor: int,
        existing_replica_node_ids: Optional[List[str]] = None
    ) -> List[NodeModel]:
        existing_ids = set(existing_replica_node_ids or [])

        # Filter candidate nodes
        candidates = [
            node for node in available_nodes
            if node.status == NodeStatus.ONLINE
            and node.node_id not in existing_ids
            and node.available_storage >= chunk.size
        ]

        if not candidates:
            raise InsufficientNodesError(
                f"No eligible ONLINE nodes with at least {chunk.size} bytes free space found for chunk {chunk.chunk_id}"
            )

        if len(candidates) < replication_factor:
            # We don't have enough distinct nodes to fulfill replication factor fully
            # Select all available candidate nodes
            selected = candidates
        else:
            # Sort candidates by available storage descending (load balance)
            sorted_candidates = sorted(candidates, key=lambda n: n.available_storage, reverse=True)
            selected = sorted_candidates[:replication_factor]

        return selected

class AIPlacementStrategy(PlacementStrategy):
    """
    Interface / Extension Point for future AI-based placement strategy.
    Can consider network latency, historical node reliability, predictive disk wear, energy usage, etc.
    Currently falls back to RuleBasedPlacementStrategy.
    """

    def __init__(self):
        self._fallback_strategy = RuleBasedPlacementStrategy()

    def select_nodes_for_chunk(
        self,
        chunk: ChunkModel,
        available_nodes: List[NodeModel],
        replication_factor: int,
        existing_replica_node_ids: Optional[List[str]] = None
    ) -> List[NodeModel]:
        # Extension point: call ML model / reinforcement learning agent here
        # Fallback to rule-based placement
        return self._fallback_strategy.select_nodes_for_chunk(
            chunk, available_nodes, replication_factor, existing_replica_node_ids
        )
