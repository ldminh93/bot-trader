---

description: "Task list for User Management (Admin)"
---

# Tasks: User Management (Admin)

**Input**: Design documents from `/specs/003-user-management/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), [quickstart.md](./quickstart.md)

**Tests**: Included — Constitution Principle II expects `pytest` coverage for this financial-reporting logic, and `quickstart.md` names the specific test files to create.

**Organization**: Tasks are grouped by user story (US1, US2, US3 — see [spec.md](./spec.md)) so each can be implemented and verified independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

Web app per [plan.md](./plan.md)'s Project Structure: `backend/apps/accounts/`, `backend/apps/trading/`, `frontend/app/`, `frontend/components/`, `frontend/lib/`.

---

## Phase 1: Setup

**Purpose**: Minimal scaffolding — this feature adds no new dependencies or services, only new files inside existing Django apps and the existing Next.js app.

- [X] T001 [P] Create `backend/apps/accounts/tests/__init__.py` (accounts app has no `tests/` package yet; needed so pytest discovers `test_me_view.py` below)

**Checkpoint**: No new tooling/dependencies required — proceed directly to Foundational.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The "who am I" endpoint is consumed by every story's frontend behavior (showing/hiding the nav link, redirecting non-admins), so it's built once here rather than duplicated per story.

**⚠️ CRITICAL**: Complete this phase before starting US1, US2, or US3 frontend work. Backend work for US1's data endpoint (Phase 3) has no dependency on this phase and may proceed in parallel.

- [X] T002 [P] Add `CurrentUserSerializer` (serializes `is_staff` of `request.user`) in `backend/apps/accounts/serializers.py`
- [X] T003 [P] Add `MeView(APIView)` (`GET`, default `IsAuthenticated`, returns `{"is_staff": bool}` via `CurrentUserSerializer`) in `backend/apps/accounts/views.py`, per contract in [contracts/api.md](./contracts/api.md#get-apiauthme)
- [X] T004 Wire `path("me", MeView.as_view())` into `backend/apps/accounts/urls.py` (depends on T003) — resolves to `GET /api/auth/me` per `backend/config/urls.py`'s `api/auth/` prefix
- [X] T005 [P] Add `api.me(): Promise<CurrentUser>` to the `api` object in `frontend/lib/api.ts` (mirrors `api.stats()` at `frontend/lib/api.ts:167`) and the `CurrentUser` type in `frontend/lib/types.ts`
- [X] T006 [P] Add `test_me_view.py` in `backend/apps/accounts/tests/` — `pytest.mark.django_db` tests using `APIClient`/`force_authenticate` (pattern from `backend/apps/trading/tests/test_trades_view.py`) covering: staff caller gets `{"is_staff": true}`, non-staff caller gets `{"is_staff": false}`, unauthenticated caller gets `401`

**Checkpoint**: `/api/auth/me` is live and typed on the frontend — all user stories can now proceed.

---

## Phase 3: User Story 1 - Admin reviews all users' performance (Priority: P1) 🎯 MVP

**Goal**: An admin opens a page and sees every registered user with win rate and total profit, matching the figures that user sees on their own stats view, with a distinct state for users who have no closed trades yet.

**Independent Test**: Log in as a staff user, open `/users`, confirm every registered user appears with the correct win rate/profit (cross-checked against that user's own `/trades` stats), and that a user with zero closed trades shows a "no trades yet" state rather than 0%.

### Tests for User Story 1

- [X] T007 [P] [US1] Add `test_user_performance_view.py` in `backend/apps/trading/tests/` — `pytest.mark.django_db` tests (pattern from `test_trades_view.py`) covering: a staff caller gets `200` with one entry per registered user; `total_profit`/`win_rate` for a seeded user with a mix of winning/losing closed trades plus one open trade match hand-computed values per [data-model.md](./data-model.md); a user with zero closed trades gets `win_rate: null`, not `0`

### Implementation for User Story 1

- [X] T008 [US1] Implement `UserPerformanceListView(APIView)` in `backend/apps/trading/views.py`, grouping `Trade` by `user` via `.values("user").annotate(...)` per the formulas in [research.md](./research.md#3-where-the-aggregation-query-lives-and-how-its-computed) and field shape in [data-model.md](./data-model.md#userperformanceentry--one-row-per-user-in-the-new-list-endpoints-response); set `permission_classes = [permissions.IsAdminUser]` (overriding the project default the same way `SystemStatusView` overrides to `AllowAny` at `backend/apps/trading/views.py:700-701`)
- [X] T009 [US1] Wire `path("users/performance", UserPerformanceListView.as_view())` into `backend/apps/trading/urls.py` (depends on T008) — resolves to `GET /api/users/performance`
- [X] T010 [P] [US1] Add `UserPerformanceEntry` type to `frontend/lib/types.ts` and `api.userPerformance(): Promise<{ results: UserPerformanceEntry[] }>` to `frontend/lib/api.ts`, per [contracts/api.md](./contracts/api.md#frontend-consumption-frontendlibapits-frontendlibtypests)
- [X] T011 [US1] Create `frontend/components/users-console.tsx` — fetch via `api.userPerformance()` on mount, render a table (mirroring the plain-Tailwind style of `frontend/components/dashboard/trade-table.tsx`) with columns username/email, win rate, total profit; render "No trades yet" for `win_rate === null`; visually distinguish rows where `is_active === false` (e.g. muted styling + badge)
- [X] T012 [US1] Create `frontend/app/users/page.tsx` — thin wrapper rendering `<UsersConsole />` inside `PageFrame` (title "Users", description summarizing the page), matching `frontend/app/trades/page.tsx`'s pattern

**Checkpoint**: Staff users can view `/users` and see accurate win rate/profit for everyone; non-staff enforcement lands in Phase 5 (US3) but `IsAdminUser` above already blocks them at the API layer — the page itself isn't yet hidden from their nav.

---

## Phase 4: User Story 2 - Admin finds top/bottom performers quickly (Priority: P2)

**Goal**: The admin can sort the list by profit or win rate (ascending/descending, deterministic tie-break by username) and search by username/email.

**Independent Test**: With several seeded users of varying performance, sort by profit then by win rate and confirm reordering in both directions; type a partial username/email into search and confirm the list narrows to matches.

### Tests for User Story 2

- [X] T013 [P] [US2] Extend `test_user_performance_view.py` (`backend/apps/trading/tests/`) with cases for `?ordering=total_profit`, `?ordering=-total_profit`, `?ordering=win_rate`, `?ordering=-win_rate` (including a tie broken by username ascending), and `?search=<substring>` matching username or email, per [contracts/api.md](./contracts/api.md#get-apiusersperformance)

### Implementation for User Story 2

- [X] T014 [US2] Add `ordering` (default `-total_profit`, secondary sort `username`) and `search` (case-insensitive substring on `username`/`email`) query-param handling to `UserPerformanceListView` in `backend/apps/trading/views.py` (depends on T008)
- [X] T015 [US2] Extend `api.userPerformance()` in `frontend/lib/api.ts` to accept `{ ordering?: string; search?: string }` and append them as query params (depends on T010)
- [X] T016 [US2] Add sortable column headers and a search input to `frontend/components/users-console.tsx`, re-fetching via `api.userPerformance()` on change (depends on T011, T015)

**Checkpoint**: US1 + US2 together give a fully usable, searchable/sortable admin view.

---

## Phase 5: User Story 3 - Non-admin access is blocked (Priority: P1)

**Goal**: A non-staff (or anonymous) user cannot view the Users page or call its data endpoint, and no user performance data leaks in any denial response.

**Independent Test**: Log in as a non-staff user; confirm no "Users" nav entry is shown, confirm navigating directly to `/users` does not display other users' data, and confirm a direct call to `GET /api/users/performance` returns `403` with no user data in the body. Confirm the same for an anonymous (logged-out) request.

### Tests for User Story 3

- [X] T017 [P] [US3] Extend `test_user_performance_view.py` (`backend/apps/trading/tests/`) with cases: non-staff authenticated caller gets `403` with a body containing no `results`/user data; unauthenticated caller gets `401`/`403` with no user data (depends on T008 existing; can be written alongside T007)

### Implementation for User Story 3

- [X] T018 [US3] Add a gated "Users" nav entry to the `navigation` array in `frontend/components/app-shell.tsx` (`frontend/components/app-shell.tsx:20-28`), calling `api.me()` (T005) on mount and rendering the entry only when `is_staff` is `true`
- [X] T019 [US3] In `frontend/app/users/page.tsx` (or `users-console.tsx`), call `api.me()` on mount and redirect to `/dashboard` when `is_staff` is `false` or the call fails, before rendering any table content (depends on T005, T012)

**Checkpoint**: All three user stories are independently functional — the feature is complete. (Note: the API-level block from `IsAdminUser` in T008 was already effective from Phase 3 onward; this phase adds the frontend-side UX for it and the tests proving it.)

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation against the spec's success criteria.

- [X] T020 Run `backend/apps/accounts/tests/test_me_view.py` and `backend/apps/trading/tests/test_user_performance_view.py` (`pytest`) and confirm all pass
- [X] T021 Execute the manual frontend verification steps in [quickstart.md](./quickstart.md#frontend-validation-manual-per-constitutions-ui-verification-rule) against `npm run dev`, confirming SC-001 through SC-005 from [spec.md](./spec.md#measurable-outcomes)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. Blocks the *frontend* portions of US1/US3 (T011, T012, T018, T019 all need `api.me()`/`CurrentUser` from T005). US1's *backend* endpoint (T008, T009) has no dependency on Phase 2 and may be built in parallel with it.
- **User Story 1 (Phase 3)**: Backend (T007-T009) can start immediately after Setup. Frontend (T010-T012) needs Phase 2 (T005) done.
- **User Story 2 (Phase 4)**: Depends on US1's `UserPerformanceListView` (T008) and `users-console.tsx` (T011) existing.
- **User Story 3 (Phase 5)**: Depends on T008 (permission gate already present), T005 (`api.me()`), and T012 (`/users` page existing).
- **Polish (Phase 6)**: Depends on all desired stories being complete.

### User Story Dependencies

- **US1 (P1)**: No dependency on US2/US3 for its own value — a staff user can already see accurate data once US1 alone is done (US3's `IsAdminUser` gate is embedded in US1's own endpoint task T008, so US1 is never shipped insecure).
- **US2 (P2)**: Builds on US1's endpoint and table; independently testable once added (sorting/search are additive query params, don't change US1's baseline behavior).
- **US3 (P1)**: The API-level denial is already true as soon as US1 ships (T008 sets `IsAdminUser` from the start); US3's own tasks are additive frontend UX (hide nav, redirect) plus the tests that prove denial at both layers.

### Parallel Opportunities

- T001 (Setup) can run alongside early planning/review.
- T002, T003, T005, T006 (Phase 2) touch different files and can run in parallel; T004 depends on T003.
- T007 (US1 tests) can be written in parallel with T008 implementation start (write test first per Constitution Principle II, confirm it fails, then implement).
- T010 (frontend types) can run in parallel with T008/T009 (backend) since they only need the contract in [contracts/api.md](./contracts/api.md), not the running implementation.
- T013 (US2 tests) can be drafted in parallel with T007 since both extend the same test file around the same view.

---

## Parallel Example: Foundational Phase

```bash
# These touch different files and can be worked on together:
Task: "Add CurrentUserSerializer in backend/apps/accounts/serializers.py"
Task: "Add MeView(APIView) in backend/apps/accounts/views.py"
Task: "Add api.me() and CurrentUser type in frontend/lib/api.ts / frontend/lib/types.ts"
Task: "Add test_me_view.py in backend/apps/accounts/tests/"
```

## Parallel Example: User Story 1

```bash
# Backend and frontend contract work can proceed together once the shape in
# contracts/api.md is agreed:
Task: "Add test_user_performance_view.py in backend/apps/trading/tests/"
Task: "Add UserPerformanceEntry type and api.userPerformance() in frontend/lib/"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Log in as staff, confirm `/users` shows accurate data (T007's assertions plus a manual spot-check against `/trades` stats for SC-004)
5. This is already safe to demo/deploy: US3's `IsAdminUser` gate is baked into T008, so there is no insecure intermediate state — non-staff users are blocked at the API from the first commit, even before the nav/redirect UX (Phase 5) exists.

### Incremental Delivery

1. Setup + Foundational → shared "who am I" plumbing ready
2. Add US1 → validate independently → deploy/demo (MVP)
3. Add US2 → validate sort/search independently → deploy/demo
4. Add US3 → validate nav-hiding/redirect UX and denial tests → deploy/demo
5. Polish → run full quickstart.md validation against all success criteria

---

## Notes

- [P] tasks touch different files with no unmet dependencies.
- Backend tests follow the existing project convention: plain `pytest.mark.django_db` functions using `rest_framework.test.APIClient` + `force_authenticate`, no fixture/factory library (see `backend/apps/trading/tests/test_trades_view.py`) — no new test infrastructure needed.
- No new models, migrations, dependencies, or services are introduced anywhere in this task list, per the Constitution Check in [plan.md](./plan.md).
- Commit after each task or logical group; stop at any Checkpoint to validate a story independently before continuing.
