#!/usr/bin/env python
"""Sustained write load for the soak: Evidence in, durable write accepted.

A soak that only samples an idle database cannot show queue or disk trends.
This driver keeps writing new Evidence and submitting them to the durable
write queue at a fixed rate, so `soak_probe.py` sees real work: queue depth,
connections, handles and on-disk growth over hours.

It writes only to the database path it is given; it never opens the daily Home.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from one_memory.database_access import close_main_databases  # noqa: E402
from one_memory.imports.models import (  # noqa: E402
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)
from one_memory.imports.storage import EvidenceStore  # noqa: E402
from one_memory.memory_server.contracts import BatchIdentity, WriteRequest  # noqa: E402
from one_memory.memory_server.durable_queue import DurableWriteQueue  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--every", type=float, default=5.0)
    parser.add_argument("--batch", type=int, default=4)
    args = parser.parse_args(argv)

    store = EvidenceStore(args.database)
    queue = DurableWriteQueue(args.database)
    end = time.monotonic() + args.seconds
    written = 0
    accepted = 0
    while time.monotonic() < end:
        ids = []
        for index in range(args.batch):
            stamp = datetime.now(UTC)
            record = store.put(
                EvidenceInput(
                    source_id="soak-driver",
                    conversation_id="soak",
                    message_id=f"soak-{stamp.timestamp()}-{index}",
                    role="user" if index % 2 else "assistant",
                    written_by=WrittenBy.PERSON if index % 2 else WrittenBy.AGENT,
                    verbatim=f"soak load {stamp.isoformat()} #{index}",
                    created_at=stamp,
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            ).record
            ids.append(record.evidence_id)
            written += 1
        batch = BatchIdentity(internal_session_id="soak-session", first_round=1, last_round=1)
        queue.submit(
            WriteRequest(
                internal_session_id="soak-session",
                batch_identity=batch,
                evidence_ids=ids,
                idempotency_key=f"soak-{time.time_ns()}",
            )
        )
        accepted += 1
        time.sleep(max(0.05, args.every))
    close_main_databases()
    print(f"written={written} accepted={accepted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
