---
status: accepted
date: 2026-11-22
supersedes: null
plan: docs/plans/2026-11-21-mcp-server
---

# ADR-0004: pandoc-mcp's layout on mcp-service-kit

## Context

The owner maintains several MCP servers, pandoc-mcp among them, built on the owner's mcp-service-kit, which provides the transports, the command line and the configuration base. A shared layout lets the owner move between servers, copy proven parts (auth, document store, upload links), and keep MCP-specific code away from the logic that tests exercise directly. scanscribe itself is used only through its public API, pinned at a Git tag.

Rejected: a flat module (it breaks with the pattern the owner maintains, and mixes MCP wiring with job logic); building on FastMCP directly without the kit (each server would repeat the transports, CLI and auth hook).

## Decision

We will follow pandoc-mcp's layout on mcp-service-kit: `server.py` for the instructions and auth, `service.py` for tool discovery and HTTP routes, one `features/<name>/tool.py` per tool, and the logic in modules that never use MCP's API (`ocr_service.py`, `jobs.py`, `documents.py`, `uploads.py`). Configuration is the kit's `BaseServerConfig` plus `ScanscribeMcpConfig` for `SCANSCRIBE_MCP_*` settings, and scanscribe is used only through `scanscribe.__all__`.

## Consequences

- A new tool is a new `features/<name>/` package with `register_tool(mcp, ocr)`; the service finds it without registration code.
- Logic stays testable without MCP, and the tools stay thin: argument checks, replies and error mapping.
- The kit's behaviour (for example refusing HTTP without an auth provider) applies here; a kit upgrade is a dependency change to review.
- Parts copied from pandoc-mcp may drift from it; changes worth sharing should go back to pandoc-mcp or into the kit.
