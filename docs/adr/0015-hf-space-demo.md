# ADR 0015: A hosted demo on a Hugging Face Space

**Status:** Accepted · **Date:** 2026-10-18 · **Amends:** [ADR 0014](0014-local-event-demo.md) (the event demo still runs
locally; this adds a public URL next to it)

## Context
The event rules prefer a live deployment. ADR 0014 kept the event demo on the laptop and the EC2 design as a plan. The
repo now ships its own demo data (26 synthetic incidents in `examples/samples/`), so a hosted copy no longer needs a
live environment to have something to show.

## Decision
- One Docker Space on Hugging Face (free CPU tier, 2 vCPU / 16 GB). FalkorDB, the API and the web app run in a single
  container behind Caddy on port 7860 (`deploy/hf/`). The browser talks to one origin, and Caddy routes `/api/*` to
  the API without buffering, so SSE streams work.
- The Space repo holds only `deploy/hf/`. Its Dockerfile clones this repo at build time, so a push to GitHub plus a
  rebuild redeploys it. The samples stay in GitHub and never go through the Space's LFS.
- The hosted demo covers Demo 1 (the committed samples) and Demo 2 (RCAEval cases, downloaded on demand). It leaves out
  Demo 3 (the OTel Demo needs ~10 GB and 8 CPUs), the fault runner, Slack / Linear delivery and the `falkordb-mcp`
  sidecar (`ask` uses the typed tools only).
- No persistence. FalkorDB runs with saving off and a password generated per boot, and a restart starts from empty
  graphs. That's acceptable because every sample replays in seconds.

## Consequences
- Judges get a URL that works without installing anything.
- Anyone with the URL can replay samples and write chat history into the demo graphs. That is fine for a demo with no
  private data (rule 6), and a restart clears it.
- The compose stack and the EC2 plan are unchanged; the Space is a third way to run the same code.
