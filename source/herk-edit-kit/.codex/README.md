# Codex setup

Open this project folder in Codex. `AGENTS.md` contains the shared workspace guide;
Codex discovers the complete skill packages in `.agents/skills/` automatically.
Use `$cut-silences`, `$cut-mistakes`, `$video-storytelling`, or natural language.

`.claude/skills/` is canonical. After changes, run:

```sh
node scripts/sync-codex-skills.mjs
node scripts/sync-codex-skills.mjs --check
```

The mirror uses real files so Windows users do not need symlink privileges.
Keep `AGENTS.md` and `CLAUDE.md` synchronized. Project configuration leaves the
student's model, authentication, sandbox, and approval settings alone.
Project settings load after the user trusts the project. Restart Codex if new
skills do not appear. Claude Code uses the canonical `.claude/skills/` files.

Official references: [skill discovery](https://learn.chatgpt.com/docs/build-skills)
and [project configuration](https://learn.chatgpt.com/docs/config-file/config-basic).
