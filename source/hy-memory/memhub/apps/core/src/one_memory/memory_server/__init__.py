"""L1 Memory Server: the single durable write path in front of the HY SDK.

Nothing outside this package may call HY directly (enforced by the A0-01 gate).
"""
