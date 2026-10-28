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

## Contributor dependency verification

`docling` is the upstream meta-package; the fork's `docling-slim` wheel owns the
`docling` Python modules. This is intentional, not two parsing implementations.
Both `parse-docling` and `semantic-worker` select the hash-pinned fork wheel.

Use uv 0.9.10 (the CI pin). After changing dependencies, run `uv lock`, review the
diff, and commit `uv.lock` together with `pyproject.toml`. CI's existing
`uv lock --check` rejects stale resolution. Validate in a fresh environment:

```sh
verification_env=$(mktemp -d /tmp/semantica-dependency-check.XXXXXX)
uv lock --check
UV_PROJECT_ENVIRONMENT="$verification_env/venv" uv sync --locked --extra semantic-worker --no-install-project --python 3.12
"$verification_env/venv/bin/python" -c 'from importlib.metadata import version; from docling.models.stages.code_formula.native_formula import transcribe_native_fraction; assert version("docling") == "2.141.0"; assert version("docling-slim") == "2.141.0+ontoscience.2"; assert version("docling-ibm-models") == "4.0.4+ontoscience.3"; assert transcribe_native_fraction([]) is None'
```

An existing `.venv` is mutable local state, not proof of the current dependency
selection. Use `uv sync --locked --extra semantic-worker` to reconcile an intended
development environment; do not reuse an old draft checkout's environment for
main validation. The fresh check above preserves those environments.

The universal contributor lock and platform-specific native constraints have
different scopes. When dependencies change, also regenerate affected native
constraints using their recorded compile commands and run native relocation
acceptance. The native acceptance checks both Docling distribution versions and
the fork's formula API. A local environment check does not release a bundle or
update OntoScience's immutable consumer pin.

The worker profiles pin OpenAI 3.37.0. Instructor's current jiter requirement
and LiteLLM's OpenAI version cap cannot coexist with that SDK. The uv conflict
declarations cover those extras and their `llm-all`/`all` aggregates; install
these integrations in a separate environment from the packaged worker. This
records the existing dependency incompatibility instead of downgrading the
worker SDK or overriding third-party version requirements.
