---
title: Union Free CPU Compute Assay
emoji: "🧮"
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
suggested_hardware: cpu-basic
---


<!-- 561-group-standards:badges:start -->
[![Red Cup Engineering](https://img.shields.io/badge/561%20Group-Red%20Cup%20Engineering-c0392b)](https://github.com/red-cup-engineering)
[![License: MIT](https://img.shields.io/badge/license-MIT-c0392b)](LICENSE)
[![Indigenous data: CARE](https://img.shields.io/badge/Indigenous%20data-CARE-4b6f44)](https://github.com/red-cup-engineering/.github/blob/main/GOVERNANCE.md)
[![Tips welcome](https://img.shields.io/badge/tips-welcome-d4a017)](https://github.com/561-group/.github/blob/main/TIPS.md)
<!-- 561-group-standards:badges:end -->

Private, deterministic, restart-safe CPU work for the Harmonious Union. The
service exposes only `GET /health`, `POST /v1/sha256`, and `POST /v1/pbkdf2`.
Both POST operations accept exactly `{"text":"..."}`; input and work are
strictly bounded. It has no shell, uploads, network-fetch operation, secrets,
model loading, or persistent state.

The repository metadata suggests CPU Basic but does not assign hardware. The
customer-side deployment assay must independently verify that both requested
and actual hardware are `cpu-basic` and that no persistent volume is attached.
