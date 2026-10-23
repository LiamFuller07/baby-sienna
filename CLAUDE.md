AGENTS.md is the guide to this repo: the five templates, the model, the commands, citations, the hard rules and what "done" means.

@AGENTS.md

Claude Code notes:
- **Skills** are in `.claude/skills/`: one per template (`data-received`, `process-map`, `process-map-ai-opportunity`, `citation-points`, `document`) and two supporting ones (`convert`, `cite`). Each opens with its template's required elements; the work is done only when `bs.py status` shows them all fulfilled.
- **Agents** are in `.claude/agents/`: `converter` (inputs to records), `author` (one section file) and `checker` (read-only review).
- **Workflows** are `.claude/workflows/convert.js` (`{ws, captured, notes?}`) and `.claude/workflows/make.js` (`{ws, section, name, brief}`). Run them with the Workflow tool's `scriptPath` and `args`.
