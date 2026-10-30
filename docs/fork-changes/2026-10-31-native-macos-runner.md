# Native release macOS runner migration

- Date: 2026-10-31
- Inspected revision: c343f61dde511e7bf6194111a001a2a128369e89
- Native owner: .github/scripts/semantic_worker_release.py::release_matrix
- Caller: .github/workflows/semantic-worker-native.yml

GitHub cancelled macOS job 124254669985 in run 41111466268 before assigning
a runner. The check annotation identifies the scheduled macOS 14 brownout and
November 2 retirement. Move the existing ARM64 release matrix to macos-15.
The locked Python/native inputs and installed-worker acceptance remain unchanged.
No alternate packaging path or runtime implementation is introduced.

Validation: release matrix tests and direct matrix output are checked locally;
real macOS bundle acceptance remains a CI gate. No product acceptance is claimed.
Upstream merge assessment: pending; retain a supported ARM64 runner in the
existing release owner when merging upstream changes.
