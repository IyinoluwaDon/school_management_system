# School portal frontend

This is the Vite/React/TypeScript client for the Django school management backend.

## Run locally

```powershell
cd frontend
npm install
npm run dev
```

The Vite development server proxies `/api` to `http://127.0.0.1:8000`, so start Django separately:

```powershell
..\.venv\Scripts\python.exe ..\manage.py runserver
```

Set `VITE_API_URL` in `.env` when the API is hosted elsewhere. Sign in with real Django user credentials — `POST /api/token/` issues the JWT pair, `Axios` attaches the access token to every request, and a 401 triggers a silent refresh via `/api/token/refresh/` before falling back to logout.

## Structure

- `src/features`: domain pages — `auth` (JWT login), `dashboard`, `attendance` (barcode scanner), `scheduling` (OR-Tools timetable + exam seating)
- `src/services`: typed HTTP client with Bearer injection and automatic token refresh
- `src/store`: persisted Zustand session state (`accessToken`, `refreshToken`, `user`)
- `src/components`: reusable route protection and UI primitives
- `src/layouts`: authenticated application shell
- `src/types`: shared API contracts, including the Domain 2 scheduling response shapes

## Scheduling module

`/scheduling` has two tabs:

- **Timetable** — pick a term/class, view the generated weekly grid, and (for `SUPER_ADMIN`/`PRINCIPAL`) trigger `POST /api/scheduling/generate-timetable/` to re-run the CP-SAT solver.
- **Exam seating** — pick an exam paper, view the per-hall seat grid, and trigger `POST /api/scheduling/generate-seating/` to re-run the seating allocator. Seats are colour-coded by class so adjacency can be checked at a glance.
