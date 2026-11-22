# Architecture decision records

ADRs record decisions that should outlive the plan that made them. `impl-plan` proposes them when a plan closes and writes them from its ADR template as `NNNN-<slug>.md`, numbered one past the highest existing ADR.

- Never edit an accepted ADR. A changed decision gets a new ADR that supersedes it.
- Smaller decisions, and decisions made outside a plan, go in the [decision log](../decision-log.md).

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-one-worker-injected-engine.md) | One OCR worker per process, with an injected engine | accepted |
| [0002](0002-http-security-model.md) | The HTTP security model | accepted |
| [0003](0003-docker-slim-gpu-wheels.md) | Docker on `python:3.12-slim` with the GPU wheels | accepted |
| [0004](0004-pandoc-mcp-layout-on-the-kit.md) | pandoc-mcp's layout on mcp-service-kit | accepted |
