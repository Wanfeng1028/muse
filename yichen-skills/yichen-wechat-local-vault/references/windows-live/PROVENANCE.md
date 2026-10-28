# Windows acquisition implementation provenance

- Read-only Config.Cipher candidate/object traversal and Windows CNG API usage adapted from [TANGandXUE/wcdb-key-tool](https://github.com/TANGandXUE/wcdb-key-tool), commit `79f1b5b92e12c66aa281b4a60a3c478b5f547dfa`, `wcdb_key_tool_windows.py`. MIT, copyright CloudDreamAI / TANGandXUE. Retained license: [WCDB_KEY_TOOL_LICENSE.txt](WCDB_KEY_TOOL_LICENSE.txt).
- Committed WAL page merger and stable-pair reading adapted from [freanocank/wechat-decrypt](https://github.com/freanocank/wechat-decrypt), commit `f0b3f9f95dda2d954ee3dbe1d139fb1944a5ecfd`, `scripts/common/wal_snapshot.py`. MIT, copyright cocofeng. Retained license: [WECHAT_DECRYPT_LICENSE.txt](WECHAT_DECRYPT_LICENSE.txt).
- Exact reviewed source hashes are in [source-lock.json](source-lock.json). These are selected source adaptations, not an installation of either upstream tool. No upstream setup, debugger, hooks, process termination, MCP server, or key persistence route is included.
- Local additions: native API signatures and handle cleanup, signed process/profile checks, bounded read-only acquisition, protected private output ACL, authenticated page decryption, complete SQLite integrity checks, chat-specific snapshot profile, isolated CLI route, and synthetic regression tests.

Primary format references: [SQLCipher design](https://www.zetetic.net/sqlcipher/design/), [SQLite WAL format](https://sqlite.org/fileformat2.html#wal_file_format), [Microsoft BCryptDecrypt](https://learn.microsoft.com/en-us/windows/win32/api/bcrypt/nf-bcrypt-bcryptdecrypt).

Runtime dependencies remain Python standard library, Windows native APIs and the existing pinned zstandard wheel. No additional network access is performed by Windows acquisition code.
