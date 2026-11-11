# Varsity Chaka

A multi-university motorcycle ride-sharing platform for verified students. Piloted with Daffodil International University (DIU). Riders and passengers are matched with an explainable score, shown an advisory cost-sharing range and an arrival-time range. It is a mobility optimization prototype, not a commercial ride-hailing service.

## Status

Work in progress (academic project). See `docs/` for requirements and architecture.

## Repository layout

```
backend/    FastAPI application, database models, services
frontend/   Jinja templates, HTMX, Leaflet, static assets
ml/         Synthetic data generator, model training and evaluation
docs/       Requirements, architecture, progress log, AI usage log
```

## Setup

1. Install Docker Desktop and Python 3.12.
2. Copy `.env.example` to `.env` and set your own passwords.
3. Start the database: `docker compose up -d`
4. Backend setup instructions are added with the first backend commit.

## Branching

- `main`: stable
- `develop`: integration
- `feature/<module>`: one branch per module, merged through pull requests
