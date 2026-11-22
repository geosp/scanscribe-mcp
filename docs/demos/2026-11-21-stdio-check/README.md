# Manual check · stdio server on the GPU · 2026-11-21

Phase 01, task 4.4 of [the plan](../../plans/2026-11-21-mcp-server/phases/01-stdio-server.md): register the server with Claude Code over stdio, and OCR a self-made PDF of a few pages through `input_path`.

> [!NOTE]
> Run by an agent (Claude Code in VS Code) after the owner installed the `gpu` extra and registered the server in an untracked project `.mcp.json`; the owner has no `claude` command on this machine.

- **Result:** pass. OCR over stdio on the GPU gives text identical to the input. The first run found that Claude Code didn't show `get_ocr_result`'s inline text; it was fixed, and the rerun passes
- **Machine:** AMD Ryzen 9 8945HS, NVIDIA GeForce RTX 3060 (driver 610.43.03), Fedora Linux 44 (kernel 7.1.7)
- **Versions:** commit 77600eb (first run) and cb621d6 (rerun after the fix); scanscribe 0.2.0, mcp-service-kit 0.2.1, fastmcp 4.2.4, paddlepaddle-gpu 3.3.1, paddleocr 3.7.0, paddlex 3.7.2
- **Who ran it:** an agent, delegated by the owner (see the note above)
- **Input:** a 3-page PDF drawn by [make_pdf.py](make_pdf.py) (sentences written for this check, at 200 dpi). No book material was used.

## Commands

```bash
cd /path/to/scanscribe-mcp
uv sync --extra gpu
uv run python docs/demos/2026-11-21-stdio-check/make_pdf.py /tmp/stdio-check/check.pdf
claude mcp add scanscribe -- uv run --directory "$PWD" scanscribe-mcp
```

Without the `claude` command (as on the machine above), put the same server in a project `.mcp.json` and reload the editor; keep that file out of Git, since it holds a local path:

```json
{"mcpServers": {"scanscribe": {"command": "uv", "args": ["run", "--directory", "/path/to/scanscribe-mcp", "scanscribe-mcp"]}}}
```

Then, in a new Claude Code session, ask:

> Use the scanscribe tools to OCR /tmp/stdio-check/check.pdf. Follow the job with get_ocr_job (wait_s 60) and report the state, step, page progress and device each time. Then get the result inline, and also write it with output_path to /tmp/stdio-check/check.txt.

Compare the text with what was drawn:

```bash
diff /tmp/stdio-check/expected.txt /tmp/stdio-check/check.txt
```

Afterwards, remove the registration if you don't want it kept: `claude mcp remove scanscribe`.

## Observations

- **Device reported by `get_ocr_job`:** `gpu:0`.
- **Pages:** 3 of 3.
- **Time:** the first job ran 5.6 s (`run_seconds`), including the engine load; no models were downloaded, because they were already in `~/.paddlex` from earlier scanscribe use. The second job ran 0.8 s on the loaded engine.
- **Steps seen while polling:** none. Both jobs had finished by the first `get_ocr_job` call (`wait_s` 5 and 10), which returned `succeeded` with page 3 of 3.
- **Text compared with `expected.txt`:** `diff` printed nothing; the text written through `output_path` (319 characters) is identical.
- **Inline result:** `get_ocr_result` without `output_path` returned `"inline": true, "chars": 319`, but the agent saw only those structured fields, not the page text. The server sends the text as a second content block next to `structuredContent`, and Claude Code passed only the structured content to the model.
- **Unknown job id:** a `get_ocr_job` call with a wrong id returned the tool error `no job with id '…'; it may have expired`.
- **Anything printed to the session that wasn't a tool reply:** nothing.

### Rerun after the fix

The server now also puts each reply's summary (`message`) and the result's text (`text`) in its structured content. After a window reload restarted the server, a third job ran 3.4 s on `gpu:0`, including a fresh engine load. `get_ocr_result` showed the agent all three pages inline, and `first_page=2, last_page=3` showed pages 2 and 3 with their markers. Both texts match `expected.txt`.
