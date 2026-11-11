# Varsity Chaka: Phase 2 System Architecture

Status: DRAFT v0.1, 11 Nov 2026. Builds on `01-requirements.md`.

## 1. Architecture style

A modular monolith. One FastAPI application with clearly separated layers, one MySQL database, plus OSRM as a separate routing container. A monolith suits a 2-person, 30-day project: one codebase to run and debug, with module boundaries that could be split into services later.

## 2. Component overview

```
Browser / installable PWA (Jinja pages + HTMX + Leaflet)
              |  HTTPS (TLS in deployment)
              v
        FastAPI application
   +---------------------------------+
   | Routers  (HTTP, validation)     |
   | Services (business logic)       |
   |   auth, rider_application,      |
   |   rides, matching, fare, eta,   |
   |   trips, safety                 |
   | Tenancy  (university scoping)   |
   | Models   (SQLAlchemy)           |
   +---------------------------------+
        |                    |
        v                    v
     MySQL 8             OSRM (Docker)
                         Bangladesh OSM extract

 ml/  (offline): synthetic data -> train -> evaluate -> saved .joblib
      loaded by the eta service at startup
```

## 3. Technology choices and why

| Concern | Choice | Reason |
|---|---|---|
| Backend | Python 3.12, FastAPI | One language for API and ML; automatic API docs for testing |
| Database | MySQL 8, SQLAlchemy, Alembic | Known to the team; Alembic gives versioned migrations that show progress |
| Passwords | Argon2 (argon2-cffi) | Modern memory-hard hash; no plain text ever stored |
| Sessions | Signed JWT in an HttpOnly cookie | Works with server-rendered pages and HTMX without exposing the token to JavaScript |
| Validation | Pydantic | Declarative input validation, automatic error responses |
| Frontend | Jinja2 + HTMX + Leaflet | Little JavaScript; partner can build quickly; mobile-friendly |
| Routing | OSRM in Docker | Free, open source, self-hosted |
| ML | scikit-learn Random Forest, pandas | In-process; no second service to deploy |
| Tests | pytest | Unit and tenant-isolation tests |

## 4. Backend layering

| Layer | Responsibility | Rule |
|---|---|---|
| Routers | Receive requests, validate, call services, return responses | No business logic |
| Services | Business rules (matching, fare, state machine) | No HTTP code; testable alone |
| Models | Database tables | No business logic |
| Tenancy | Resolve the user's university and scope every query | Used by every service touching tenant data |
| Core | Config, database session, security helpers | Shared utilities |

## 5. Folder structure

```
varsity-chaka/
  backend/
    app/
      main.py
      core/        config.py, database.py, security.py
      models/      user.py, university.py, rider.py, ...
      schemas/     Pydantic request/response models
      routers/     auth.py, riders.py, rides.py, ...
      services/    auth_service.py, matching_service.py, ...
      tenancy/     context.py, scoping helpers
    alembic/       migrations
    tests/
    requirements.txt
  frontend/
    templates/     Jinja pages and HTMX partials
    static/        css, js, icons, manifest.json
  ml/
    data/          synthetic generator
    train_eta.py
    evaluate_eta.py
    models/        saved models (not committed)
  docs/
```

The backend mounts `frontend/templates` and `frontend/static`, so the frontend developer works only inside `frontend/` and the backend developer only inside `backend/` and `ml/`.

## 6. Multi-tenancy design

- Each tenant-owned table has a non-null `university_id` with a foreign key and an index.
- On login, the user's `university_id` is stored in the signed token and is also re-read from the database on each request. It is never taken from request input.
- A `TenantContext` dependency gives every route the current user and university.
- All service functions take the context and filter by `university_id` through one shared helper, so a forgotten filter is a code-review catch, not a silent leak.
- Reading a record by ID also checks its `university_id`; a record from another tenant returns "not found", not "forbidden", so existence is not revealed.
- Super admin has no `university_id` and can only use tenant-management routes.
- Tests: create two tenants with data, log in as a user of tenant A, and assert that every list and detail endpoint returns nothing from tenant B.

## 7. Authentication and authorization

- Registration: email must match the tenant's allowed domain; Pydantic validates fields; password strength rules enforced; password hashed with Argon2.
- Email verification: signed, expiring link. For the demo, the link is printed in the server log when no mail server is configured, and this is stated in the report.
- Login: rate-limited; generic error message for wrong email or password.
- Roles: `super_admin`, `university_admin`, `student`. Rider capability is a separate approved rider profile, not a role string, so one student can be both.
- Authorization: FastAPI dependencies such as `require_role(...)` and `require_approved_rider()`, applied on the server for every route.
- No credentials in source code. Demo accounts come from a seeder script that reads values from `.env` and hashes passwords.

## 8. API conventions

- Page routes return HTML for browsers and HTMX; data routes live under `/api/v1/...` and return JSON.
- JSON envelope: `{"success": true, "data": ..., "error": null}` and on failure `{"success": false, "data": null, "error": {"code": "...", "message": "..."}}`.
- Standard status codes: 400/422 validation, 401 unauthenticated, 403 forbidden, 404 not found.
- Timestamps stored in UTC and displayed in Asia/Dhaka.

## 9. Intelligent modules and how they integrate

| Module | v1 implementation | Label | Where it runs |
|---|---|---|---|
| Matching | Hard filters + weighted score + template explanation | Rule-based, explainable | `services/matching_service.py` |
| Fare range | Formula from distance, time, traffic, fuel, efficiency, capped demand | Rule-based, explainable | `services/fare_service.py` |
| ETA | OSRM base duration corrected by a Random Forest trained on synthetic data; range from tree spread | Prototype (synthetic data) | `services/eta_service.py` loads `ml/models/eta.joblib`; falls back to a time-of-day multiplier if missing |

Only the ETA module uses a trained model, and its evaluation will state that the data is synthetic.

## 10. Live location

The rider's trip screen posts coordinates every 10-20 s (or after about 30-50 m of movement) to a trip-scoped endpoint. The server accepts them only for the assigned rider on an `in_progress` trip. The passenger's screen polls the latest position for that trip only. Position rows are deleted after the trip per the retention rule.

## 11. Security summary

TLS in deployment, Argon2 hashing, HttpOnly cookies, CSRF protection for form posts, input validation, server-side authorization on every route, private upload folder outside static serving, tenant scoping, audit log for admin actions, secrets in `.env` only.

## 12. Environment and cross-platform setup

- Docker Compose runs MySQL (and OSRM in a later step) identically on macOS and Windows.
- Python 3.12 virtual environment in `backend/.venv`.
- `.gitattributes` enforces LF endings; `.env` is never committed.

## 13. Ownership

| Area | Owner |
|---|---|
| Database design, migrations, auth backend, tenancy, matching, fare, ETA, ML | Sajid |
| Frontend templates and design system, auth screens, match screens, admin screens | Partner |
| Rider application and approval (backend and database) | Partner, with review by Sajid |

Each person commits their own work under their own GitHub account and explains it in the viva.

## 14. Schedule to the 10 Dec assessment

| Dates | Work |
|---|---|
| 11-14 Nov | Foundation, ER diagram, DB migrations (Phase 3) |
| 15-19 Nov | Authentication module, tenant scoping, auth screens (demo-ready) |
| 20-25 Nov | Rider application and admin approval |
| 26 Nov-2 Dec | Ride posts and requests, matching with explanations |
| 3-6 Dec | Fare range, OSRM and ETA model |
| 7-8 Dec | Trip lifecycle and live location, tests, ML evaluation |
| 9 Dec | Demo rehearsal, personal reports finalised |
| 10 Dec | Assessment |

Commits continue through the whole period, including after the core features are working, so the history shows recent progress.

## 15. Open technical items

1. Hosting for the demo is a laptop, so no deployment work is needed beyond a clean run script.
2. Mail for verification links is simulated through the log for the demo.
3. The motorcycle-aware OSRM profile is deferred; the limitation is documented.
