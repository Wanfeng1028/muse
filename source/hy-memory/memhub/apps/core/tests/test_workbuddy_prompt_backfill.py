"""When the prompt hook's capture fails, the transcript file is what brings the words in.

WorkBuddy's Stop carries `last_assistant_message`, so Stop capture records the
reply only and never reads the transcript for the person's line. What is left
for a lost prompt is live file sync. This runs the real reader, OS watch and
Core routes; the hook side is the same `capture_hook` the CLI runs.
"""

import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.imports.sources.registry import build_source_catalog
from one_memory.live_capture import capture_hook
from tests.source_consent import connection_request
from tests.test_four_app_live_ingest import eventually, write_turn

INJECTED = (
    '<system-reminder data-role="hook"><memhub_memory_context>\n'
    "以下是 MemHub 按当前消息自动检索到的历史记忆\n[1] 旧记忆\n"
    "</memhub_memory_context></system-reminder>"
)


def _rows(database: Path, text: str) -> list[tuple[str, str]]:
    with closing(sqlite3.connect(database)) as db:
        return db.execute(
            """
            SELECT e.evidence_id, group_concat(o.origin, ',')
            FROM evidence e JOIN evidence_origins o ON o.evidence_id = e.evidence_id
            WHERE e.source_id = 'workbuddy' AND e.verbatim = ?
            GROUP BY e.evidence_id
            """,
            (text,),
        ).fetchall()


def test_file_sync_brings_in_a_prompt_the_hook_lost_and_never_doubles_one_it_kept(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("one_memory.model_presets._preset_data", lambda: None)

    async def scenario() -> None:
        home = tmp_path / "home"
        root = home / ".workbuddy/projects"
        root.mkdir(parents=True)
        transcript = root / "rollout-native.jsonl"
        write_turn(transcript, "workbuddy", "initial", "user", "开场原话")
        settings = Settings(
            data_dir=tmp_path / "data",
            source_home=home,
            api_token=SecretStr("isolated-test"),
            automatic_memory_processing=False,
            live_sync_interval_seconds=3600,
            live_sync_watch_debounce_seconds=0.05,
            live_sync_watch_min_interval_seconds=0.2,
        )
        database = settings.data_dir / "one-memory.sqlite3"
        app = create_app(settings, source_catalog=build_source_catalog(home=home, environment={}))
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer isolated-test"},
            ) as client,
        ):
            connected = await client.post(
                "/api/v1/sources/connect",
                json=await connection_request(
                    client,
                    ["workbuddy"],
                    onboarding=True,
                    full_rescan=True,
                    enable_sync=True,
                ),
            )
            assert connected.status_code == 200
            await eventually(lambda: app.state.evidence_store.count() == 1)
            assert (await client.post("/api/v1/onboarding/complete")).status_code == 200
            watch = app.state.live_sync_watch
            assert watch is not None and watch.watching == ("workbuddy",)
            await asyncio.sleep(0.2)

            # 1. The hook's capture was lost: only the file has the words.
            lost = "钩子没采到的这句：表头要固定"
            write_turn(transcript, "workbuddy", "turn-lost", "user", f"{lost}\n{INJECTED}")
            await eventually(lambda: len(_rows(database, lost)) == 1, timeout=10)

            # 2. The hook kept the words first; the file's copy is the same line.
            kept = "钩子采到的这句：列宽可拖动"
            assert capture_hook(
                "workbuddy",
                {"hook_event_name": "UserPromptSubmit", "session_id": "native", "prompt": kept},
                database,
            )
            assert [origins for _id, origins in _rows(database, kept)] == ["hook"]
            write_turn(transcript, "workbuddy", "turn-kept", "user", f"{kept}\n{INJECTED}")
            await eventually(lambda: "file" in (_rows(database, kept) or [("", "")])[0][1])

            # Positive control for the count above: a hook row the file cannot
            # match to (another session id) does stay a second copy.
            other = "会话号对不上的这句：底色换浅灰"
            assert capture_hook(
                "workbuddy",
                {"hook_event_name": "UserPromptSubmit", "session_id": "elsewhere", "prompt": other},
                database,
            )
            write_turn(transcript, "workbuddy", "turn-other", "user", other)
            await eventually(lambda: len(_rows(database, other)) == 2, timeout=10)
            await eventually(lambda: not watch._workers)

            assert len(_rows(database, lost)) == 1
            assert sorted(_rows(database, kept)[0][1].split(",")) == ["file", "hook"]
            assert len(_rows(database, kept)) == 1

    asyncio.run(scenario())
