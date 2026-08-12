# Feature Specification: User Management (Admin)

**Feature Branch**: `003-user-management`

**Created**: 2026-08-12

**Status**: Draft

**Input**: User description: "Add an admin-only 'User Management' page where staff/admin users can view a list of all registered users along with each user's win rate and total profit, computed from their trading history (aggregating the existing Trade model's realized_pnl and win/loss counts, similar to the existing per-user TradeStatsView logic but across all users). Regular (non-staff) users must not be able to access this page or its underlying API."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Admin reviews all users' performance (Priority: P1)

An admin wants a single place to see how every registered user is performing, so they open the User Management page and see a list of all users with their win rate and total profit.

**Why this priority**: This is the core value of the feature — without it, there is no way to compare user performance without manually checking each account. Everything else builds on this list existing.

**Independent Test**: Can be fully tested by logging in as an admin, opening the User Management page, and confirming every registered user appears with a win rate and total profit value that matches what that user sees on their own trading stats.

**Acceptance Scenarios**:

1. **Given** an admin is logged in, **When** they open the User Management page, **Then** they see a list of all registered users, each showing username/email, win rate, and total profit.
2. **Given** a user has closed trades with a mix of wins and losses, **When** the admin views that user's row, **Then** the displayed win rate and profit match the figures that user would see on their own dashboard.
3. **Given** a user has no closed trades, **When** the admin views that user's row, **Then** the row shows a clear "no trades yet" state instead of an error or a misleading 0%.

---

### User Story 2 - Admin finds top/bottom performers quickly (Priority: P2)

An admin wants to quickly spot the best and worst performing users, so they sort or search the list by profit or win rate instead of scanning every row manually.

**Why this priority**: Once the list exists (P1), sorting/searching is what makes it actually useful for oversight at scale rather than a static dump of data.

**Independent Test**: Can be fully tested by loading the page with several users of varying performance, then sorting by profit and by win rate, and confirming the order updates correctly; and by searching for a username/email and confirming the list filters to matching users.

**Acceptance Scenarios**:

1. **Given** the user list is displayed, **When** the admin sorts by total profit, **Then** users are reordered from highest to lowest (or lowest to highest) profit.
2. **Given** the user list is displayed, **When** the admin sorts by win rate, **Then** users are reordered accordingly.
3. **Given** the user list is displayed, **When** the admin types a username or email into a search field, **Then** the list narrows to matching users only.

---

### User Story 3 - Non-admin access is blocked (Priority: P1)

A regular (non-staff) user must not be able to view other users' performance data, whether by navigating to the page directly or by calling the underlying data endpoint.

**Why this priority**: This is a privacy/security requirement equal in importance to the page existing at all — shipping the list without this control would leak every user's trading performance to every other user.

**Independent Test**: Can be fully tested by logging in as a non-admin user and attempting to open the page URL and call the underlying data endpoint directly, confirming both are refused.

**Acceptance Scenarios**:

1. **Given** a non-admin user is logged in, **When** they navigate to the User Management page URL, **Then** they are denied access (e.g., redirected or shown an access-denied state) and see no other users' data.
2. **Given** a non-admin user is logged in, **When** their client calls the underlying data endpoint directly, **Then** the request is refused and no user performance data is returned.
3. **Given** an anonymous (logged-out) visitor, **When** they attempt to reach the page or endpoint, **Then** they are redirected to login and no data is exposed.

---

### Edge Cases

- What happens when a user has trades but all are still open (no closed trades yet)? Win rate should show a "no closed trades" state rather than 0% or an error.
- What happens when there are a very large number of registered users? The list must remain usable (e.g., via pagination) rather than loading everything at once and degrading performance.
- What happens when two or more users are tied on profit or win rate while sorting? Order between tied users should be stable and deterministic (e.g., secondary sort by username).
- What happens if a user's account is deactivated/disabled? They should still be visible to the admin (for auditing) but should be clearly distinguishable from active users.
- What happens if profit or win rate figures are recalculated while the admin has the page open (new trades closing in the background)? Stale data is acceptable until the admin refreshes; the page does not need to be live-updating for v1.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST restrict access to the User Management page and its underlying data to admin/staff users only.
- **FR-002**: System MUST deny access to the page and its underlying data for any non-admin (including anonymous) request, without revealing any user performance data in the denial response.
- **FR-003**: System MUST display a list of all registered users to an authorized admin.
- **FR-004**: For each user in the list, system MUST display a total profit figure computed from that user's trading history, consistent with the definition already used on that user's own stats view.
- **FR-005**: For each user in the list, system MUST display a win rate computed from that user's closed trades, consistent with the definition already used on that user's own stats view.
- **FR-006**: System MUST display a distinct "no trades yet" / "no closed trades" state for users who have no closed trades, rather than showing a misleading 0% win rate.
- **FR-007**: System MUST allow the admin to sort the user list by total profit and by win rate, in ascending or descending order.
- **FR-008**: System MUST allow the admin to search/filter the user list by username or email.
- **FR-009**: System MUST support viewing the full set of registered users without the page becoming unusably slow as the number of users grows (e.g., via pagination or incremental loading).
- **FR-010**: System MUST visually distinguish deactivated/disabled user accounts from active ones in the list.

### Key Entities

- **User**: A registered account. Key attributes relevant here: username/email, active/disabled status, admin/staff status.
- **Trade**: A user's individual trade record (already exists), including outcome (open/closed), realized and unrealized profit, and close time. Used as the source data for the aggregated figures below.
- **User Performance Summary** *(derived, not newly stored)*: Per-user aggregation shown in the list — total profit (realized + unrealized across that user's trades) and win rate (share of closed trades that were profitable).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An admin can view win rate and total profit for every registered user on a single page without visiting any per-user screen.
- **SC-002**: An admin can identify the top 5 and bottom 5 performing users in under 30 seconds using sorting, regardless of total user count.
- **SC-003**: 100% of access attempts to the page or its data by non-admin or anonymous users are blocked, with zero user performance data disclosed in the response.
- **SC-004**: The performance figures shown for a user on this page always match the figures that same user sees on their own personal stats view (zero discrepancy).
- **SC-005**: The user list remains responsive (loads and becomes interactive in under 2 seconds under normal load) regardless of total registered user count.

## Assumptions

- "Total profit" and "win rate" use the same definitions already established for a user's own trading stats (realized + unrealized profit; win rate = profitable closed trades ÷ total closed trades).
- "Admin/staff" maps to the existing account-level admin designation already used to gate the separate back-office admin tools; this feature does not introduce a new roles/permissions system, only a new consumer of the existing admin designation.
- Granting or revoking admin/staff status itself is out of scope for this feature — it continues to be managed through existing account administration, not through this new page.
- A tabular list view is sufficient for v1; charts/visualizations of performance trends are out of scope.
- Drilling down from this list into an individual user's full trade history is out of scope for v1 and may be considered as a future enhancement.
- Performance figures may lag slightly behind real-time trading activity (eventual consistency is acceptable); live/streaming updates are out of scope for v1.
