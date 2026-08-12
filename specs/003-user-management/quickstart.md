# Quickstart: Validating User Management (Admin)

## Prerequisites

- Backend and frontend running per `README.md` (`docker compose up` or the local dev instructions), with at least two user accounts:
  - One admin: `python manage.py createsuperuser` (or set `is_staff=True` on an existing user via Django shell/admin).
  - One regular (non-staff) user, e.g. registered via the app's normal sign-up flow.
- At least one of those users should have a few closed and/or open `Trade` rows (create via the existing paper-trading flow, or via Django admin at `/admin/`) so the list isn't showing only empty states.

## Backend contract checks

```bash
# 1. As the admin user (JWT access token from /api/auth/login):
curl -H "Authorization: Bearer <admin_access_token>" \
  http://localhost:8000/api/users/performance
# Expect 200 with a "results" array covering every registered user.

curl -H "Authorization: Bearer <admin_access_token>" \
  http://localhost:8000/api/auth/me
# Expect 200 {"is_staff": true}

# 2. As the non-admin user:
curl -H "Authorization: Bearer <regular_access_token>" \
  http://localhost:8000/api/users/performance
# Expect 403, no user data in the body.

curl -H "Authorization: Bearer <regular_access_token>" \
  http://localhost:8000/api/auth/me
# Expect 200 {"is_staff": false}

# 3. Anonymous:
curl http://localhost:8000/api/users/performance
# Expect 403/401, no user data in the body.
```

## Frontend validation (manual, per Constitution's UI verification rule)

1. `npm run dev` in `frontend/`.
2. Log in as the **regular** user → confirm no "Users" nav entry appears, and navigating directly to `/users` redirects away without showing any data (User Story 3 / FR-002).
3. Log in as the **admin** user → confirm a "Users" nav entry appears; open it.
4. On `/users`, confirm:
   - Every registered user appears with username/email, win rate, and total profit (User Story 1).
   - A user with no closed trades shows a "no trades yet" state rather than `0%` (Edge Cases).
   - A deactivated user (toggle `is_active` off via Django admin) is visually distinguished (FR-010).
   - Sorting by profit and by win rate reorders the list correctly in both directions (User Story 2).
   - Typing a username/email into search narrows the list (User Story 2).
5. Cross-check: for the admin's own account, confirm the win rate/profit shown on `/users` exactly matches what that same account sees on its own `/trades` stats view (SC-004).

## Automated coverage (per Constitution Principle II)

- `backend/apps/trading/tests/test_user_performance_view.py` (new): non-staff and anonymous requests get `403`/`401` with no data; staff request returns all users; win_rate/total_profit values match hand-computed expectations from seeded `Trade` fixtures; zero-closed-trades user gets `win_rate: null`; `ordering` and `search` params behave as documented in `contracts/api.md`.
- `backend/apps/accounts/tests/test_me_view.py` (new): returns the correct `is_staff` value for staff and non-staff callers; `401` when unauthenticated.

## Follow-up (out of scope for this feature, noted for later)

- If the registered-user count grows large enough that an unpaginated `/api/users/performance` response becomes slow, add DRF `PageNumberPagination` to that view (see `research.md` §4) — no response-shape change needed beyond wrapping `results` with pagination metadata.
