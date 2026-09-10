# School Management System

A Django REST backend + React/Vite/TypeScript frontend school portal (attendance, academics,
scheduling, exams, finance, HR, library, transport, and more).

## Backend setup

```bash
python -m venv venv
# Windows: venv\Scripts\activate | macOS/Linux: source venv/bin/activate
pip install -r requirements.txt

# This project defaults to Postgres (see .env). For a quick local run without
# Postgres installed, override the engine for just this shell session:
#   export DB_ENGINE=django.db.backends.sqlite3 DB_NAME=dev.sqlite3   (macOS/Linux)
#   $env:DB_ENGINE="django.db.backends.sqlite3"; $env:DB_NAME="dev.sqlite3"  (PowerShell)

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Run the test suite with `python manage.py test` (25 tests, ~1 second).

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`, so run the two together.

## This sprint: Domain 1 (Auth) + Domain 2 (Algorithmic Optimization)

### Domain 1 — Authentication & Security

- `djangorestframework` + `djangorestframework-simplejwt` configured with `SIMPLE_JWT` settings
  (30-min access / 7-day refresh tokens, rotation + blacklist on refresh).
- `POST /api/token/` — returns `{access, refresh, user}`. `user` includes role, display name,
  and digital barcode token so the frontend can populate its session in one call.
- `POST /api/token/refresh/` — exchanges a refresh token for a new access token.
- `GET /api/auth/me/` — resolves the current user from a Bearer token (session restore on reload).
- `accounts/authentication.py` adds `jwt_login_required` / `jwt_role_required` decorators so the
  project's existing plain-Django views (not DRF viewsets) gained real Bearer-token auth and RBAC
  without a full rewrite. Student/parent-facing endpoints are scoped to the caller's own
  student/children; scheduling generation is restricted to `SUPER_ADMIN` / `PRINCIPAL`.
- Frontend: `LoginPage` posts real credentials, `store/auth.ts` persists the JWT pair, and
  `services/api.ts` attaches `Authorization: Bearer <token>` to every request and transparently
  refreshes on a 401 before falling back to logout.

### Domain 2 — Algorithmic Optimization Engine

`school/scheduling.py`:

- **`generate_timetable(term, ...)`** — Google OR-Tools CP-SAT model.
  - Hard constraints: no teacher, class, or room is ever double-booked in the same slot.
  - Soft constraint: subjects flagged `Subject.is_difficult` are spread across different days per
    class instead of clustering (implemented as a minimized penalty, not a hard rule, so it never
    makes an otherwise-solvable problem infeasible).
  - `POST /api/scheduling/generate-timetable/` — `{term_id, room_ids?, weekdays?, periods_per_day?,
    period_minutes?, day_start?, replace_existing?}` → persists `TimetableEntry` rows.
- **`allocate_exam_seating(paper, ...)`** — greedy, adjacency-checking seat allocator.
  - Always seats the largest remaining class group next, skipping a seat only when it would place
    a student beside/behind a same-class neighbour *and* an alternative group is available —
    succeeds fully whenever a conflict-free arrangement exists, and reports `unresolved_adjacencies`
    when one class is simply too large to fully separate from itself.
  - Distributes across multiple halls (`ExamPaper.room` + `overflow_rooms`).
  - `POST /api/scheduling/generate-seating/` — `{paper_id, room_ids?, columns?}`.
  - `GET /api/scheduling/seating/<paper_id>/` — the seating plan grouped by hall, with grid
    dimensions, for rendering.
- Supporting model additions: `Subject.is_difficult`, `SubjectAssignment.periods_per_week`,
  `Room.rows`/`Room.columns` (+ `Room.seating_grid` for an auto square-grid fallback),
  `ExamPaper.overflow_rooms`, `ExamCandidate.room`/`row`/`column`.
- Frontend: `/scheduling` has **Timetable** (term/class pickers, weekly grid, generate button) and
  **Exam seating** (paper picker, per-hall seat grid colour-coded by class, generate button) tabs.
- Reference-data endpoints added to support the pickers above: `GET /api/terms/`, `/api/classes/`,
  `/api/rooms/`, `/api/exams/papers/`.

### Still open (Domains 3 & 4 from the original sprint spec)

- PDF report cards / exam slips (WeasyPrint or ReportLab).
- Payment gateway integration (Paystack/Flutterwave) + webhook-driven invoice status updates.
- SMS/email notification service (Twilio/SendGrid) wired to absence and discipline events.
- Frontend: Academics grade-entry grid, Finance dashboard + "Pay Now", and the remaining
  placeholder routes (HR, Leaves, Profile editing) as functional CRUD screens.
