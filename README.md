---
title: Union Free CPU Compute Assay
emoji: "🧮"
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
suggested_hardware: cpu-basic
---


Private, deterministic, restart-safe CPU work for the Harmonious Union. The
service exposes only `GET /health`, `POST /v1/sha256`, and `POST /v1/pbkdf2`.
Both POST operations accept exactly `{"text":"..."}`; input and work are
strictly bounded. It has no shell, uploads, network-fetch operation, secrets,
model loading, or persistent state.

The repository metadata suggests CPU Basic but does not assign hardware. The
customer-side deployment assay must independently verify that both requested
and actual hardware are `cpu-basic` and that no persistent volume is attached.
