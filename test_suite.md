# Test Suite

Primary context docs:
- `docs/CURRENT_STATE.md`
- `docs/APPLICATION_SPECS.md`
- `docs/PROJECT_ARCHITECTURE_TODO.md`

Canonical test-suite documentation is maintained here:
- `test_suite.md`

Recommended context-loading order for future work:
1. `docs/CURRENT_STATE.md`
2. `docs/APPLICATION_SPECS.md`
3. `docs/PROJECT_ARCHITECTURE_TODO.md`
4. `docs/fashion-ai-architecture.jsx`

Use this command to run all tests:
```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```
