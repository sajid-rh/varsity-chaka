# AI Usage Log

Tool used: Claude (Anthropic). Every entry lists what I asked, what I used, and how I checked it. I read and ran the output myself before committing it.

| Date | What I asked (representative prompt) | What I used | How I checked it |
|---|---|---|---|
| 7-10 Nov 2026 | "Here are my project requirements. Help me plan before we build." | Scope decisions, three core features, team ownership split, the 30-day schedule | Reviewed with my partner and the faculty rules |
| 10 Nov 2026 | "Write the Phase 1 requirements document." | docs/01-requirements.md as a starting draft | Read it fully and edited what I disagreed with |
| 11 Nov 2026 | "Design the system architecture and the database." | docs/02-architecture.md and docs/03-database-design.md | Compared against the requirements; asked why for each table |
| 11 Nov 2026 | "Create the backend skeleton: settings, database session, health check." | FastAPI app, config, database session, health endpoint, one test | Ran pytest (1 passed) and opened /api/v1/health with the database reporting up |
| 11 Nov 2026 | "Set up Alembic and the first migration for tenancy and user tables." | Alembic setup, five models, migration 001 | Read the generated migration, applied it, and inspected the tables in MySQL |
| 12 Nov 2026 | "Implement Phase 2: ride offers, requests, explainable matching engine, trip state machine, and safety blocks." | Migration 003, ride models, matching service, trip service, block service, API routers and tests | Ran full test suite (139 passed), tested tenant isolation, single passenger DB capacity constraint, and 30-min auto-complete |

## Notes

- Claude does not have access to my computer. I ran every command myself and fixed the setup problems on my own machine.
- I write my individual report myself, in my own words.
