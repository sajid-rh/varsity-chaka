# Varsity Chaka: Phase 1 Requirements

Status: DRAFT for team approval. Version 0.1, 10 Nov 2026.

## 1. Product summary

Varsity Chaka is a multi-university motorcycle ride-sharing platform for verified students. A rider who is already travelling to campus (or home) offers a seat. A verified passenger of the same university requests it. The system ranks matches with an explainable score, suggests an advisory cost-sharing range, and predicts an arrival-time range. It is a mobility optimization product, not a commercial ride-hailing service.

- First tenant: Daffodil International University (DIU).
- A second demo tenant (for example AIUB) is seeded to demonstrate and test data isolation.
- Deadline: 7 Dec 2026. Team: 2 people.

## 2. Decisions log (approved)

| # | Decision |
|---|---|
| D1 | Name: Varsity Chaka |
| D2 | Multi-university SaaS; DIU is the first tenant |
| D3 | Shared MySQL database; `university_id` on every tenant-owned table; scoping enforced in the backend; cross-tenant access tests |
| D4 | Matching only within the same university |
| D5 | Payment outside the app; app shows an advisory range only; bKash and card are documented future work |
| D6 | Rider approval expires after 2 years; also revoked on plate/license change or loss of student status |
| D7 | One passenger per motorcycle (capacity fixed at 1) |
| D8 | Free tools only; no live traffic API; traffic awareness from time-of-day and day-of-week patterns |
| D9 | No real data; synthetic trips, always labeled synthetic in code and report |
| D10 | Stack: Python, FastAPI, MySQL (SQLAlchemy + Alembic), scikit-learn, OSRM (Docker), HTMX + Leaflet, PWA |
| D11 | Live location by polling every 10-20 s while the trip screen is open |
| D12 | ML data stays per tenant; no cross-tenant pooling in this version |
| D13 | SOS button creates a high-priority incident for the university admin |
| D14 | Demo runs on a laptop |

## 3. User roles

| Role | Scope | Description |
|---|---|---|
| Super Admin | Platform | Creates universities (tenants), assigns university admins, sees platform health. Does not browse student personal data. |
| University Admin | One university | Approves riders, reviews incidents, sets fare policy and safety rules, manages campus destinations and branding. |
| Rider | One university | A verified student with an approved motorcycle who offers rides. |
| Passenger | One university | A verified student who requests rides. A student can hold both Rider and Passenger roles. |

### Permission matrix

Y = allowed, O = own records only, T = within own tenant only, "-" = no.

| Action | Super Admin | Uni Admin | Rider | Passenger |
|---|---|---|---|---|
| Create/disable university | Y | - | - | - |
| Create university admin | Y | - | - | - |
| Configure tenant settings (branding, destinations, fare policy, weights) | - | T | - | - |
| Register and verify email | - | - | Y | Y |
| Submit rider application | - | - | O | - |
| Approve/reject/suspend rider | - | T | - | - |
| Post ride offer | - | - | O | - |
| Request ride and view ranked matches | - | - | - | O |
| Accept/decline request | - | - | O | - |
| Share live location | - | - | O | - |
| View rider live location (active trip only) | - | - | - | O |
| Report, block, SOS | - | - | Y | Y |
| Review incidents | - | T | - | - |
| Request own data deletion | - | - | O | O |
| Process deletion request | - | T | - | - |

All checks are enforced server-side. Hiding a button in the UI is never treated as protection.

## 4. Functional requirements

Priority: M = must, S = should, F = future.

### 4.1 Tenancy and administration

| ID | Requirement | Pri |
|---|---|---|
| FR-T1 | Each university has its own workspace: name, logo/colors, allowed email domain, campus destinations | M |
| FR-T2 | Every tenant-owned record carries `university_id`; every query is scoped by it | M |
| FR-T3 | Automated tests confirm a user from tenant A cannot read or modify tenant B data | M |
| FR-T4 | University admin edits fare policy (per-km ceiling, demand adjustment on/off), matching weights, search limits | S |
| FR-T5 | Super admin creates tenants and assigns university admins | M |

### 4.2 Accounts and verification

| ID | Requirement | Pri |
|---|---|---|
| FR-A1 | Registration with university email; domain must match the tenant | M |
| FR-A2 | Email verification before any other action | M |
| FR-A3 | Optional student ID number for admin cross-check | S |
| FR-A4 | Password hashing (Argon2 or bcrypt), login rate limiting | M |
| FR-A5 | Role-based access control as server-side dependencies | M |
| FR-A6 | Passenger and rider roles on one account | M |

### 4.3 Rider application

| ID | Requirement | Pri |
|---|---|---|
| FR-R1 | Application: motorcycle model, engine class, plate number, registration card photo, license-status declaration, helmet declaration | M |
| FR-R2 | Admin reviews, approves, rejects (with reason) or suspends; checks plate manually against the BRTA Service Portal | M |
| FR-R3 | Approval expires after 2 years and requires re-verification | M |
| FR-R4 | Approval revoked if plate/license details change or student status ends | S |
| FR-R5 | Uploaded documents stored privately, visible only to that tenant's admins | M |
| FR-R6 | Pre-ride helmet confirmation each time a ride starts | S |

### 4.4 Rides and trip lifecycle

| ID | Requirement | Pri |
|---|---|---|
| FR-L1 | Rider posts an offer: origin, destination, departure time, direction (to/from campus) | M |
| FR-L2 | Passenger posts a request: pickup, destination, preferred time | M |
| FR-L3 | Capacity is 1; a second booking on an active ride is rejected | M |
| FR-L4 | Trip follows the state machine in section 6 | M |
| FR-L5 | Completion needs confirmation from both users; auto-complete after 30 minutes if one confirms and the other is silent; disputes are flagged | M |
| FR-L6 | Contact details revealed only to the matched counterpart after confirmation; each disclosure logged | M |

### 4.5 Matching (explainable)

| ID | Requirement | Pri |
|---|---|---|
| FR-M1 | Hard filters: same tenant, rider verified and approved and not expired, rider available, seat free, time within window, pickup distance and detour within limits, no block between the pair | M |
| FR-M2 | Score from pickup proximity, route overlap (direction-aware), rider detour, departure-time gap, destination compatibility, rider reliability | M |
| FR-M3 | Reliability score from completion rate, average rating, on-time rate, with smoothing so new riders are not over- or under-trusted | M |
| FR-M4 | Each result shows an explanation generated from the actual score components | M |
| FR-M5 | Weights stored as tenant settings, with sensible defaults | S |
| FR-M6 | Before confirmation the passenger sees only approximate information (distance band, area-level pickup) | M |

### 4.6 Cost-sharing range

| ID | Requirement | Pri |
|---|---|---|
| FR-F1 | Range computed from distance, predicted time, traffic level, fuel price, bike class efficiency, demand level | M |
| FR-F2 | Demand adjustment is capped and can be switched off by the tenant | M |
| FR-F3 | Output states main factors in plain language and is labeled advisory and voluntary | M |
| FR-F4 | Fuel price and per-km ceiling are admin-editable settings | M |

### 4.7 ETA

| ID | Requirement | Pri |
|---|---|---|
| FR-E1 | OSRM provides distance, base duration and geometry | M |
| FR-E2 | Random Forest predicts the correction to the OSRM duration from hour, day of week, distance, route type and other features | M |
| FR-E3 | Output is an arrival range (for example 8:18-8:25 AM) from the spread of tree predictions | M |
| FR-E4 | During an active trip, the range is recomputed from the rider's current position | S |
| FR-E5 | Training data is synthetic and labeled as such; a rule-based fallback is used if the model is unavailable | M |
| FR-E6 | Crowdsourced GPS traffic estimation | F |

### 4.7a Live location

| ID | Requirement | Pri |
|---|---|---|
| FR-G1 | Rider consents per trip | M |
| FR-G2 | Location is shared only while the trip is in progress, enforced by the server | M |
| FR-G3 | Updates every 10-20 s, or earlier after meaningful movement | M |
| FR-G4 | Sharing stops automatically on completion or cancellation | M |
| FR-G5 | Passenger sees "last updated N seconds ago" | S |

### 4.8 Safety and privacy

| ID | Requirement | Pri |
|---|---|---|
| FR-S1 | Report with categories (no helmet, second passenger, unsafe riding, harassment, no-show, other) | M |
| FR-S2 | Block user; blocked pairs never match | M |
| FR-S3 | Post-ride feedback (1-5 rating, tags, optional comment); visible after both submit | M |
| FR-S4 | SOS button creates a high-priority incident | S |
| FR-S5 | Admin incident queue: new, under review, action taken, dismissed; actions: warn, suspend, de-approve, ban | M |
| FR-S6 | Audit log of every admin action | M |
| FR-S7 | Data deletion request processed by the admin: profile anonymized, documents and GPS traces deleted, incident records kept for a set period | S |
| FR-S8 | Reports alone never auto-suspend; they raise a flag for admin review | M |

## 5. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | Security: TLS for all traffic including internal calls, hashed passwords, encrypted private uploads, server-side authorization, input validation |
| NFR-2 | Isolation: no cross-tenant read or write, proven by automated tests |
| NFR-3 | Privacy: sensitive fields minimized in responses, no exact home location before confirmation |
| NFR-4 | Performance: match list under 2 s and ETA under 1 s for a demo-size dataset |
| NFR-5 | Usability: mobile-first layout, installable PWA, works on small screens |
| NFR-6 | Maintainability: modular services (matching, fare, ETA separate), consistent API response shape, tests per module |
| NFR-7 | Reproducibility: identical setup on macOS and Windows via Docker and a pinned Python version |
| NFR-8 | Honesty: every ML component labeled as rule-based, prototype or trained; no claimed accuracy without evaluation results |

## 6. Trip state machine

`requested` -> `accepted` -> `confirmed` -> `in_progress` -> `completed`

`cancelled` is reachable from every state before `completed`. A `disputed` flag may be set on a trip when the two completion confirmations disagree.

| State | Passenger sees | Location sharing |
|---|---|---|
| requested | Match list, approximate info | Off |
| accepted | Rider acceptance, approximate info | Off |
| confirmed | Contact details, exact pickup | Off until the rider starts |
| in_progress | Live rider location and ETA range | On |
| completed / cancelled | Summary, feedback form | Off, enforced by server |

## 7. Main use cases

1. **UC1 Register and verify.** Student registers with university email, verifies it, and lands in their own university workspace.
2. **UC2 Become a rider.** Student submits the rider application; the admin reviews and approves; the student can now post offers.
3. **UC3 Post a ride.** An approved rider posts origin, destination and departure time.
4. **UC4 Find a ride.** Passenger posts a request; the system filters, ranks and explains matches; passenger picks one.
5. **UC5 Accept and confirm.** Rider accepts; both confirm; contact details are revealed.
6. **UC6 Take the trip.** Rider confirms helmet, starts the trip; passenger sees live location and the ETA range.
7. **UC7 Complete and rate.** Both confirm completion, then submit feedback; reliability scores update.
8. **UC8 Report or block.** Either user reports or blocks; the admin reviews the incident and records an action.
9. **UC9 SOS.** A user taps SOS; a high-priority incident reaches the admin.
10. **UC10 Delete my data.** User requests deletion; the admin processes it.
11. **UC11 Onboard a university.** Super admin creates a tenant and its admin; the admin configures branding, destinations and policy.

## 8. Out of scope (documented future work)

- In-app payments (bKash, card)
- Crowdsourced GPS traffic model
- Native mobile app with background tracking
- Learned matching ranker
- Cross-university matching
- Live traffic API
- Automated BRTA verification (no public API known)

## 9. Known limitations to state in the report

- PWA cannot track GPS reliably with the screen locked; the rider keeps the trip screen open.
- OSRM car profile approximates motorcycle travel; correction is learned from synthetic data only.
- No real trip data exists, so ML results measure the pipeline, not real-world accuracy.
- Declarations (license, helmet) are self-reported, not verified.
- Bangladesh data-protection law is evolving; the design follows common privacy-by-design principles and makes no compliance claim.

## 10. Team setup (macOS + Windows)

- Python 3.12 pinned in `.python-version` and `requirements.txt` with exact versions.
- MySQL and OSRM run in Docker through one `docker-compose.yml`, so both machines behave identically. Docker Desktop is needed on both.
- OSRM needs the Bangladesh OpenStreetMap extract and a few GB of RAM and disk; this is checked in the first setup step.
- `.gitattributes` forces LF line endings so Mac and Windows commits don't conflict.
- `.env` files are never committed; `.env.example` is.
- Repo layout: `backend/`, `frontend/`, `ml/`, `docs/`.

## 11. Revised schedule (deadline 7 Dec 2026)

| Dates | Focus |
|---|---|
| 10-14 Nov | Approve Phase 1, architecture, ER diagram, repo and Docker setup. Partner: wireframes and design system. |
| 15-20 Nov | Migrations, auth, tenant scoping, rider application and approval |
| 21-26 Nov | Ride posts, requests, trip state machine, matching |
| 27 Nov-2 Dec | Fare, ETA, live location, safety features, admin incidents |
| 3-5 Dec | Integration, tests, ML evaluation |
| 6-7 Dec | Report, demo rehearsal, buffer |

The schedule is tighter than before. If we slip, the first items to cut are SOS, data-deletion automation, and per-tenant weight editing.

## 12. Open items for approval

1. Confirm the permission matrix and the 2-year approval revocation rules.
2. Confirm the 30-minute auto-complete rule.
3. Confirm that a second demo tenant is seeded.

