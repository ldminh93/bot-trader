# Feature Specification: Fix Top Movers Auto-Sync Reliability

**Feature Branch**: `002-fix-top-movers-sync`

**Created**: 2026-07-31

**Status**: Draft

**Input**: User description: "the current sync top movers is not working" (reported alongside a
screenshot of the Top Movers screen: "Auto-register top movers to scanner" enabled, Top 20,
"auto-synced every 15 min", with "Last synced: 7/22/2026, 8:22:54 AM" — over a week stale relative
to the reported date of 2026-07-31).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automatic sync actually runs on its own (Priority: P1)

As an operator with auto-register enabled, I expect the top-movers scanner list to refresh itself
every 15 minutes without me having to click "Sync now", so that newly trending symbols get picked
up and symbols that fell out of the top movers get dropped without manual intervention.

**Why this priority**: This is the reported problem — the "last synced" time is not advancing on
its own, meaning operators who rely on hands-off auto-registration are not actually getting the
coverage they configured and believe they have.

**Independent Test**: With auto-register enabled and without clicking "Sync now", wait longer than
one sync interval (15+ minutes) and confirm the "last synced" time has advanced and the scanner
list reflects the current top movers.

**Acceptance Scenarios**:

1. **Given** auto-register is enabled and the last automatic sync happened more than 15 minutes
   ago, **When** the sync interval elapses, **Then** the system performs a new automatic sync and
   the "last synced" time advances, with no action required from the operator.
2. **Given** the operator clicks "Sync now", **When** the request completes successfully, **Then**
   the "last synced" time updates immediately, exactly as it does today — this manual path is not
   the part that is broken and must keep working unchanged.
3. **Given** auto-register has been enabled for more than one sync interval, **When** the operator
   reopens the Top Movers screen without touching "Sync now", **Then** the "last synced" time shown
   reflects a recent automatic sync, not a stale timestamp from before auto-register was last
   toggled on.

---

### Edge Cases

- What happens when an automatic sync attempt fails for one operator (e.g., a transient upstream
  market-data error)? The failure MUST NOT permanently stop that operator's future scheduled syncs,
  and MUST NOT affect other operators' scheduled syncs.
- What happens when the operator turns auto-register off and back on? The next scheduled sync MUST
  resume on the normal cadence without requiring a manual "Sync now" click to "kick-start" it.
- What happens if no one has the Top Movers screen open when a scheduled sync is due? The sync MUST
  still run in the background — it MUST NOT depend on the screen being open or on any user
  interaction.
- The existing rules for which symbols get added, removed, or kept (for example, never removing a
  symbol that still has an open position) are out of scope for this fix and MUST remain unchanged —
  only the reliability of the recurring trigger is being fixed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST automatically re-sync each operator's top-movers scanner list on a
  fixed recurring interval (currently every 15 minutes) whenever auto-register is enabled for that
  operator, without requiring a manual "Sync now" click.
- **FR-002**: The "last synced" time shown to the operator MUST reflect the most recent successful
  sync, whether it was triggered automatically or manually.
- **FR-003**: If an automatic sync attempt fails for one operator, the system MUST continue
  attempting future scheduled syncs for that operator on the normal cadence rather than stopping
  permanently after one failure.
- **FR-004**: A failed automatic sync for one operator MUST NOT prevent or delay scheduled syncs for
  any other operator.
- **FR-005**: The manual "Sync now" action MUST continue to work exactly as it does today and MUST
  NOT be altered by this fix.
- **FR-006**: This fix MUST NOT change which symbols get registered, removed, or protected (e.g.,
  open-position skip behavior) — only the reliability of the automatic recurring trigger is in
  scope.
- **FR-007**: This fix is scoped to making the automatic recurring sync actually run on schedule.
  It does not add any new "stale sync" warning indicator — the operator confirmed the only problem
  is that automatic sync never fires (manual "Sync now" already works every time); once the
  automatic path is reliable, the existing "last synced" display is sufficient.

### Key Entities

- **Auto Scanner Settings**: Per-operator configuration — whether auto-register is enabled, how
  many top gainers/losers to track, and the time of the last successful sync.
- **Sync Attempt**: A single execution (scheduled or manually triggered) that compares the current
  top movers against the operator's registered scanner list and adds, removes, or keeps symbols
  accordingly.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With auto-register enabled and no manual "Sync now" clicks, the "last synced" time
  advances at least once every 20 minutes (a modest buffer over the 15-minute interval) during
  normal operation.
- **SC-002**: When the upstream data lookup fails for one operator's sync attempt, unaffected
  operators still receive their next scheduled sync on time.
- **SC-003**: Manual "Sync now" continues to complete successfully and update "last synced"
  immediately, with no change in behavior observed by the operator.

## Assumptions

- The operator confirmed directly: manual "Sync now" works every time it is clicked; the automatic
  15-minute sync never fires on its own. This is the exact and only problem in scope.
- "Not working" means the scheduled sync is not updating state on its 15-minute cadence — evidenced
  by a "last synced" timestamp far older than 15 minutes while auto-register remains enabled — not
  that the sync runs but registers the wrong symbols.
- The existing symbol add/remove/skip rules (including the open-position protection) are correct as
  they stand today and are not part of this fix.
