> **Before you submit:** make sure you followed the [issue workflow in CONTRIBUTING.md](https://github.com/semantica-agi/semantica/blob/main/CONTRIBUTING.md#-working-on-an-existing-issue) — wait for the issue to be assigned to you before opening a PR, to avoid duplicate work.

## Description

<!-- Provide a clear description of your changes -->

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Performance improvement
- [ ] Code refactoring

## Related Issues

<!-- Link related issues using keywords like "Closes", "Fixes", "Resolves" -->

Closes #
Fixes #

## Changes Made

<!-- List the main changes in this PR -->

- 
- 
- 

## Native Capability Assessment (required for implementation changes)

<!-- Follow /AGENTS.md. Documentation-only changes may mark this section N/A. -->

- Inspected fork revision:
- Capability and existing native owner (file/symbol), or evidence it is absent:
- Actual callers, configuration and relevant tests inspected:
- Recent removals/refactors checked; why this does not restore a retired path:
- Decision: reuse / repair existing owner / add genuinely absent capability:
- Obsolete implementations removed and consumers migrated (if applicable):

- [ ] This change introduces no second implementation, alternate prompt/algorithm,
      or fallback for an existing native capability.
- [ ] Regression evidence covers the native owner and affected callers, including
      existing no-network/no-model-call guarantees where applicable.

## Fork Change Record (required for every change)

- Record path in `docs/fork-changes/`:
- [ ] The record describes why/how, inspected native ownership, affected files,
      verification and known limitations, distinguishing plans from results.
- [ ] Upstream merge risks and keep/adapt/drop criteria are recorded; merge
      resolutions preserve earlier decisions and append the new assessment.

## Testing

<!-- Describe how you tested your changes -->

- [ ] Tested locally
- [ ] Added tests for new functionality
- [ ] Package builds successfully (`python -m build`)

### Test Commands

```bash
# Build the package
pip install build
python -m build

# Optional: Run your own tests
pytest tests/

# Optional: Format code
black semantica/
isort semantica/
```

## Documentation

- [ ] Updated relevant documentation
- [ ] Added code examples if applicable
- [ ] Updated API reference if adding new APIs
- [ ] Updated cookbook if adding new examples
- [ ] No documentation changes needed

## Breaking Changes

**Breaking Changes**: [Yes/No]

<!-- If yes, describe the impact and migration path -->

## Checklist

- [ ] My code follows the project's style guidelines
- [ ] I have performed a self-review of my code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] My changes generate no new warnings
- [ ] Package builds successfully

## Additional Notes

<!-- Any additional information for reviewers -->
