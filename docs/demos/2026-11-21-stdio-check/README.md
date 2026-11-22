# Manual check · stdio server on the GPU · 2026-11-21

Phase 01, task 4.4 of [the plan](../../plans/2026-11-21-mcp-server/phases/01-stdio-server.md): register the server with Claude Code over stdio, and OCR a self-made PDF of a few pages through `input_path`.

> [!NOTE]
> Prepared by an agent; **not run yet**. The owner runs it and fills in every `TODO`.

- **Result:** TODO pass / fail, in one line
- **Machine:** TODO CPU, GPU (e.g. RTX 3060, driver version) and OS
- **Versions:** commit TODO (`git rev-parse --short HEAD`); scanscribe v0.2.0, mcp-service-kit v0.2.1, fastmcp TODO, paddlepaddle-gpu TODO, paddleocr TODO (`uv pip list | grep -Ei 'paddle|fastmcp'`)
- **Who ran it:** TODO
- **Input:** a 3-page PDF drawn by [make_pdf.py](make_pdf.py) (sentences written for this check, at 200 dpi). No book material was used.

## Commands

```bash
cd /path/to/scanscribe-mcp
uv sync --extra gpu
uv run python docs/demos/2026-11-21-stdio-check/make_pdf.py /tmp/stdio-check/check.pdf
claude mcp add scanscribe -- uv run --directory "$PWD" scanscribe-mcp
```

Then, in a new Claude Code session, ask:

> Use the scanscribe tools to OCR /tmp/stdio-check/check.pdf. Follow the job with get_ocr_job (wait_s 60) and report the state, step, page progress and device each time. Then get the result inline, and also write it with output_path to /tmp/stdio-check/check.txt.

Compare the text with what was drawn:

```bash
diff /tmp/stdio-check/expected.txt /tmp/stdio-check/check.txt
```

Afterwards, remove the registration if you don't want it kept: `claude mcp remove scanscribe`.

## Observations

- **Device reported by `get_ocr_job`:** TODO (expected `gpu:0`)
- **Pages:** TODO (expected 3)
- **Time:** TODO s from `start_ocr_job` to `succeeded` (first job, including model download if any: TODO yes/no), and TODO s for a second run
- **Steps seen while polling:** TODO
- **Text compared with `expected.txt`:** TODO (identical / differences)
- **Anything printed to the Claude Code session or the MCP log that wasn't a tool reply:** TODO
