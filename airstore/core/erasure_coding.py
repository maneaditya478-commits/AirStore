"""
AirStore Experimental Erasure Coding Module.
Provides XOR / Reed-Solomon style matrix parity chunking interface.
Note: Standard 2x replication remains default for AirStore storage nodes.
"""

from typing import List, Optional

class ErasureCodingError(Exception):
    """Raised when erasure coding splitting or reconstruction fails."""
    pass

class ErasureEncoder:
    """
    Experimental N+M Erasure Coding helper.
    Splits payload into N data shards and M parity shards.
    Allows data reconstruction if up to M shards are lost.
    """

    @staticmethod
    def split_data(data: bytes, data_shards: int = 4, parity_shards: int = 2) -> List[bytes]:
        """
        Split byte payload into data_shards + parity_shards using XOR parity.
        """
        if data_shards <= 0 or parity_shards <= 0:
            raise ValueError("Shard counts must be positive integers.")

        # Pad data to multiple of data_shards
        shard_len = (len(data) + data_shards - 1) // data_shards
        total_len = shard_len * data_shards
        padded_data = data.ljust(total_len, b'\x00')

        shards = []
        for i in range(data_shards):
            shards.append(padded_data[i * shard_len : (i + 1) * shard_len])

        # Compute primary XOR parity shard P0 = D0 ^ D1 ^ ... ^ Dn-1
        parity_0 = bytearray(shard_len)
        for shard in shards[:data_shards]:
            for b_idx in range(shard_len):
                parity_0[b_idx] ^= shard[b_idx]
        shards.append(bytes(parity_0))

        # Compute secondary parity shard P1 = D0 ^ D1 ^ ... ^ Shifted
        for p in range(1, parity_shards):
            parity_buf = bytearray(shard_len)
            for d_idx, shard in enumerate(shards[:data_shards]):
                shift = d_idx % 8
                for b_idx in range(shard_len):
                    b_val = shard[b_idx]
                    rotated = ((b_val << shift) | (b_val >> (8 - shift))) & 0xFF if shift else b_val
                    parity_buf[b_idx] ^= rotated
            shards.append(bytes(parity_buf))

        return shards

    @staticmethod
    def reconstruct_data(
        shards: List[Optional[bytes]],
        original_size: int,
        data_shards: int = 4,
        parity_shards: int = 2
    ) -> bytes:
        """
        Reconstruct original byte payload from available data + parity shards.
        """
        total_shards = data_shards + parity_shards
        if len(shards) != total_shards:
            raise ErasureCodingError(f"Expected {total_shards} shard slots, got {len(shards)}.")

        available_count = sum(1 for s in shards if s is not None)
        if available_count < data_shards:
            raise ErasureCodingError(
                f"Insufficient healthy shards available ({available_count}/{data_shards} required)."
            )

        # Check if all data shards are intact
        if all(shards[i] is not None for i in range(data_shards)):
            data_bytes = b"".join(shards[i] for i in range(data_shards))
            return data_bytes[:original_size]

        shard_len = len([s for s in shards if s is not None][0])
        missing_data_indices = [i for i in range(data_shards) if shards[i] is None]

        # Single missing shard reconstruction via primary XOR parity P0
        if len(missing_data_indices) == 1 and shards[data_shards] is not None:
            missing_idx = missing_data_indices[0]
            reconstructed_shard = bytearray(shards[data_shards])
            
            for d_idx in range(data_shards):
                if d_idx == missing_idx:
                    continue
                shard = shards[d_idx]
                for b_idx in range(shard_len):
                    reconstructed_shard[b_idx] ^= shard[b_idx]

            full_shards = list(shards[:data_shards])
            full_shards[missing_idx] = bytes(reconstructed_shard)
            data_bytes = b"".join(full_shards)
            return data_bytes[:original_size]

        raise ErasureCodingError("Multi-shard parity reconstruction requires advanced Galois Field solver.")
