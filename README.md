# Tool.py external corpus

This repository is a public, runnable corpus for exercising code-topology and
impact-analysis tools. Its Angular/Express application contains deliberate
architectural and performance stress cases. Those corpus signals are kept
separate from the analysis harness so the repository remains useful for
regression tests.

## Native baseline

```bash
npm ci
npm run lint
npm test -- --watch=false
npm run build
```

These commands validate the corpus application without requiring the Python
analysis tool.

## Run with an external `ai_studio_tool`

The analyzer is intentionally not vendored into this corpus. Point the server
at a checked-out tool directory containing `hott_kernel.py`:

```bash
AI_STUDIO_TOOL_DIR=/absolute/path/to/tools/ai_studio_tool npm run build
AI_STUDIO_TOOL_DIR=/absolute/path/to/tools/ai_studio_tool npm run serve:ssr:app
```

The application analyzes its current working directory by default. Set
`AI_STUDIO_CORPUS_ROOT=/absolute/path/to/another/repo` to use a different
explicit corpus root.

Current kernel-backed endpoints:

- `GET /api/python-info`
- `GET /api/topology`
- `GET /api/impact?file=src/app/app.ts`
- `GET /api/outline?file=src/app/app.ts`
- `GET /api/brief?file=src/app/app.ts`

Target paths are resolved inside `AI_STUDIO_CORPUS_ROOT`; traversal outside the
configured corpus is rejected. Removed standalone-analyzer routes return HTTP
`410` with the supported replacements instead of pretending their deleted
scripts still exist.

For reproducible external audits, record the corpus commit SHA, tool commit or
artifact checksum, native command results, and analysis graph signature. Treat
static findings as hypotheses until runtime evidence confirms runtime claims.
