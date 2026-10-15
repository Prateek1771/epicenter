@AGENTS.md

## Claude-specific notes

- Work one phase at a time from [docs/phases/](docs/phases/README.md). Before coding, read the phase file and the
  design-doc sections it links; don't work from the phase file alone.
- Tick task checkboxes in the phase file as tasks land, and check the phase's "Done when" before moving on.
- Before calling a change done, review it with the repo skill in `.agents/skills/code-review-and-quality/`.
- If an LLD query fails on the pinned FalkorDB tag, fix the query in [docs/LLD.md](docs/LLD.md) first, then the code.
- Ask before running anything that changes an example environment (`faults.py`, `docker stop`) or deletes graphs (`GRAPH.DELETE`, `docker compose down -v`).
