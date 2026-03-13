# Test Suite

Primary context docs:
- `docs/CURRENT_STATE.md`
- `docs/APPLICATION_SPECS.md`

Canonical test-suite documentation is maintained here:
- `docs/TEST_SUITE.md`

Recommended context-loading order for future work:
1. `docs/CURRENT_STATE.md`
2. `docs/APPLICATION_SPECS.md`
3. `docs/fashion-ai-architecture.jsx`

Use this command to run all tests:
```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Use this command for the focused agentic application eval harness:
```bash
python3 ops/scripts/run_agentic_eval.py
```

Use this command to include the live HTTP smoke flow:
```bash
USER_ID=your_completed_user_id python3 ops/scripts/run_agentic_eval.py --smoke
```
