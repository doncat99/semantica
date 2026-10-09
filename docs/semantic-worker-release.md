---
title: "Semantic Worker Release"
description: "The required remote build and release procedure for OntoScience semantic worker bundles."
icon: "package"
---

# Semantic Worker Release

Semantic worker releases are built on GitHub Actions from the Semantica fork. The local checkout is for code changes and focused validation only; it is not a source for production release assets.

## Required flow

1. Commit the Semantica changes and push the commit to the user fork.
2. Run `Semantic Worker Native Release` with `workflow_dispatch`, or push the configured `ontoscience-semantic-worker-*` tag.
3. The Ubuntu job builds the platform independent Python wheel.
4. The wheel is passed to each platform job through a short lived Actions artifact.
5. macOS, Linux, and Windows independently build their own native bundle from the wheel and their platform locked inputs.
6. Each platform runs relocation acceptance and uploads only its final archive, manifest, and acceptance receipt as an Actions artifact.
7. The publish job runs only after every platform job succeeds. It creates the GitHub Release and uploads the wheel plus all platform assets.
8. OntoScience downloads the completed Release assets, verifies every digest, updates its immutable pin, and only then builds the App.

## Boundaries

- GitHub Actions builds the wheel and all native bundles. Do not use a locally built wheel for the published Release.
- Actions artifacts are workflow-internal transport only. A Release is created once, by the final publish job.
- The native bundle is platform-specific: `darwin-arm64`, `linux-x64`, and `win-x64`.
- The Semantica fork may be pushed; the upstream repository must remain read-only.
- A failed or partial workflow must not be pinned by OntoScience. Delete or repair the failed Release before retrying with the same revision.

## Verification record

Record the workflow URL, source revision, Release tag, every asset name and GitHub digest, and the acceptance receipts before changing the OntoScience pin.
