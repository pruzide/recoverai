# Hackathon Submission Checklist

## Code & Tests
- [x] Full pytest suite green: `python -m pytest -q`
- [x] Alembic migrations apply cleanly: `python -m alembic upgrade head`
- [x] No secrets in repo (`.env` gitignored; only `.env.example` committed)
- [x] `requirements.txt` complete (includes streamlit, langgraph, celery)

## Documentation
- [x] `system-design.md` covers Milestones 1–12
- [x] `decisions.md` D-001–D-049
- [x] `challenges.md` C-001–C-019 (real problems only)
- [x] `failure-lab.md` Labs 1–12
- [x] `demo-script.md` rehearsed
- [x] `README.md` quick start + architecture

## Evidence
- [ ] Screenshots: dashboard Overview / Metrics / Cases / Simulation
- [ ] Screenshot: Swagger UI at /docs
- [ ] Screenshot: pytest output
- [ ] Screenshot: simulation terminal output with SIMULATED BENCHMARK banner
- [ ] Screenshot: one failure-lab run (Lab 4 or Lab 8)
- [ ] Git log showing incremental milestone commits

## Live Demo Readiness
- [ ] `docker compose ps` shows healthy db + redis
- [ ] `.\scripts\run_all.ps1` boots all five services
- [ ] `http://127.0.0.1:8000/health` returns 200
- [ ] `http://localhost:8501` loads with Demo Merchant data
- [ ] Webhook → recovery → captured flow rehearsed end-to-end
- [ ] Fallback plan rehearsed (pre-seeded cases + audit trail if live demo fails)

## Submission
- [ ] Repository access granted to judges
- [ ] Submission form completed
- [ ] Demo video recorded (optional but recommended)