# PR #5 Review Notes — Fact-Checking Agent MVP

Approved with follow-up items. Address before next iteration.

---

## Critical

- [ ] **String format injection** (`fact_checker.py`)
  `VERDICT_PROMPT.format(claim=claim, evidence=evidence)` crashes if claim/evidence contains `{`/`}`.
  Fix: use `.replace("{claim}", claim).replace("{evidence}", evidence)`.

- [ ] **Unhandled Verdict enum conversion** (`fact_checker.py`)
  `Verdict(worst)` raises `ValueError` if LLM returns an unexpected string.
  Fix: wrap in try/except and fall back to `Verdict.UNVERIFIABLE`.

- [ ] **Prompt injection** (`fact_checker.py`)
  User input goes directly into LLM prompts with no sanitization. Add max-length validation and document the risk.

---

## High

- [ ] **No rate limiting on parallel API calls** (`fact_checker.py`)
  `asyncio.gather()` fires N simultaneous Tavily + OpenRouter calls. Add `asyncio.Semaphore(3)` to cap concurrency.

- [ ] **Missing API endpoint tests** (`tests/`)
  No tests for `/api/v1/analysis` endpoints — auth, ownership checks (user A accessing user B's message), 404 handling.

- [ ] **No error handling in `create_analysis()` endpoint** (`analysis.py`)
  Unhandled agent crash → raw 500 with no logging. Wrap `run_analysis()` in try/except and raise a clean `HTTPException`.

- [ ] **`openrouter_api_key` not validated at startup** (`config.py`)
  Missing key fails silently at runtime. Add `@field_validator` to raise at startup if unset.

---

## Medium

- [ ] **Source attribution lost**
  Per-claim sources are merged into a flat global list. `detailed_breakdown` should preserve sources per claim.

- [ ] **Verdict aggregation not documented**
  One FALSE out of 10 TRUE claims → overall FALSE. Intentional? Document or reconsider the strategy.

- [ ] **Magic calibration numbers** (`fact_checker.py`)
  Confidence adjustment factors (`0.3`, `0.5`, `0.75`, etc.) are hardcoded with no rationale. Move to Settings or add a comment.

- [ ] **No input length limit** (`fact_checker.py` `check()`)
  Unbounded text input can spike LLM token costs. Add a max-length guard.
