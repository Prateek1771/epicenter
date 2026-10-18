---
title: Epicenter
emoji: 🎯
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Graph-native root cause analysis on FalkorDB
---

# Epicenter (hosted demo)

Epicenter finds where an outage started. It keeps a FalkorDB graph of the system, searches it upstream from the alert,
and checks every suspect with a Fault Simulator. Source, setup and docs: https://github.com/Prateek1771/epicenter

This Space runs FalkorDB, the API and the web app in one container. To try it, open `/incidents` and press
**Run a sample incident**, or pick any of the 26 synthetic samples on `/runs`.

What this hosted demo leaves out: the live OpenTelemetry Demo shop (it needs ~10 GB and 8 CPUs, so run it locally),
Slack and Linear delivery, and persistence. A restart starts from empty graphs, and every sample replays on demand.

The Space builds from the GitHub repo's `main` branch. After a push, use "Factory rebuild" in the Space settings.
