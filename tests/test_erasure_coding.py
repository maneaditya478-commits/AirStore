import pytest
from airstore.core.erasure_coding import ErasureEncoder, ErasureCodingError

def test_erasure_coding_split_and_reconstruct():
    payload = b"AirStore experimental erasure coding payload bytes 1234567890"
    
    # Split into 4 data + 2 parity shards
    shards = ErasureEncoder.split_data(payload, data_shards=4, parity_shards=2)
    assert len(shards) == 6

    # Test complete reconstruction
    reconstructed = ErasureEncoder.reconstruct_data(shards, original_size=len(payload), data_shards=4, parity_shards=2)
    assert reconstructed == payload

    # Test single missing data shard reconstruction
    damaged_shards = list(shards)
    damaged_shards[1] = None  # Simulate data shard 1 loss
    
    reconstructed_damaged = ErasureEncoder.reconstruct_data(damaged_shards, original_size=len(payload), data_shards=4, parity_shards=2)
    assert reconstructed_damaged == payload

def test_erasure_coding_insufficient_shards():
    payload = b"Test payload bytes"
    shards = ErasureEncoder.split_data(payload, data_shards=4, parity_shards=2)
    
    # Simulate losing 3 shards (only 3 surviving, but 4 required)
    damaged_shards = list(shards)
    damaged_shards[0] = None
    damaged_shards[1] = None
    damaged_shards[2] = None

    with pytest.raises(ErasureCodingError):
        ErasureEncoder.reconstruct_data(damaged_shards, original_size=len(payload), data_shards=4, parity_shards=2)
