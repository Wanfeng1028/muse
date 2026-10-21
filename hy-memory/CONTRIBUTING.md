# Contributing to Hy Memory

Thank you for your interest in contributing to Hy Memory! This document provides guidelines for contributing.

This repository also contains the MemHub application under `memhub/`. Hy Memory
is the SDK and engine; MemHub is the product and release name. Historical
`One Memory` / `one-memory` identifiers remain in compatibility interfaces.

## Development Setup

```bash
git clone https://github.com/Tencent-Hunyuan/Hy-Memory.git
cd Hy-Memory
pip install -e ".[dev,all]"
```

## Running Tests

```bash
pytest tests/ -v
```

For MemHub development:

```bash
cd memhub
pnpm install
uv sync --directory apps/core --all-groups --locked
pnpm check
```

Changes that affect both components should include focused SDK tests at the
repository root and MemHub tests under `memhub/`.

### Graph backend tests (Kuzu / Neo4j)

The graph end-to-end tests are parameterized over both backends. Kuzu is embedded
and always runs; Neo4j is **skipped unless you point it at a live instance**:

```bash
docker run -d --name hy-neo4j-test -p 7688:7687 \
  -e NEO4J_AUTH=neo4j/testpassword neo4j:5.26-community

HY_TEST_NEO4J_URL=bolt://localhost:7688 \
HY_TEST_NEO4J_USER=neo4j \
HY_TEST_NEO4J_PASSWORD=testpassword \
  pytest tests/test_memory_graph.py -v
```

Please run these before touching `data/graph_store_neo4j.py`. Cypher differs
enough between the two engines that Kuzu-only runs have shipped real bugs — e.g.
Neo4j rejects `ORDER BY` on a variable that is not projected after
`RETURN DISTINCT`, and several graph methods swallow exceptions and return empty,
so a broken query looks like "no data" rather than an error.

> The tests wipe all `Memory` / `Topic` / `VdbRef` / `User` nodes in the target
> Neo4j database, so point them at a throwaway instance, never a shared one.

## Code Style

- Follow PEP 8
- Use type hints for function signatures
- Write docstrings for public APIs

## Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes with clear messages
4. Push to your fork and open a Pull Request

## Adding a New Vector Store Backend

1. Create `hy_memory/data/vector_store_yourbackend.py` implementing `VectorStoreBase`
2. Register it in `hy_memory/data/vector_store.py` factory function
3. Add configuration fields to `hy_memory/config.py` if needed
4. Document the new backend in `docs/env_reference.md`

## Adding a New LLM Provider

Hy Memory uses the OpenAI-compatible protocol. If your LLM provider supports the OpenAI API format (most do), it works out of the box by setting `MEMORY_LLM_BASE_URL`.

## Reporting Issues

- Use [GitHub Issues](https://github.com/Tencent-Hunyuan/Hy-Memory/issues) for
  bug reports and feature requests
- Include your Python version, OS, and relevant configuration
- For bugs, include steps to reproduce
- Report vulnerabilities through the private channel in
  [`SECURITY.md`](SECURITY.md), not in a public issue

## License

Contributions are licensed under the root Apache-2.0 License. Third-party
components remain subject to their existing licenses and attribution notices.
