# Feature Specification: Block Overextended Long Entries

**Feature Branch**: `001-block-overextended-long`

**Created**: 2026-07-31

**Status**: Draft

**Input**: User description: "i want to adjust the logic to open long postion in case price is higher then MA signal we dont open long position."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bot skips a chased long entry (Priority: P1)

As the bot operator, when the market price has already moved above the
moving-average reference line the bot uses to judge a long setup, I want the
bot to skip opening a new long position rather than buying into an
already-extended move.

**Why this priority**: This is the entire feature — it directly changes
whether a real (paper or live) long order gets placed, which affects trading
outcomes on every evaluation cycle.

**Independent Test**: Feed the bot a market snapshot where price sits above
the configured MA reference line and every other existing long-entry
condition is satisfied. Confirm no long position is opened and a skip reason
referencing the MA condition is recorded.

**Acceptance Scenarios**:

1. **Given** a symbol that otherwise qualifies for a long entry, **When** the
   current price is above the configured MA reference line by more than the
   allowed margin, **Then** the bot does not open a long position and logs the
   reason.
2. **Given** a symbol that otherwise qualifies for a long entry, **When** the
   current price is at or within the allowed margin of the configured MA
   reference line, **Then** the bot's decision to open a long position is
   unaffected by this rule.
3. **Given** a symbol with an already-open long position, **When** price
   subsequently moves above the configured MA reference line, **Then** this
   rule does not close the position or otherwise alter exit/stop management
   for that position.

---

### Edge Cases

- What happens when the moving-average reference value cannot be calculated
  (e.g., not enough price history yet)? The bot MUST treat this as "cannot
  confirm price is within range" and skip the long entry, consistent with the
  project's paper-first safety posture of failing closed rather than open.
- What happens at the exact boundary, where price equals the MA reference
  value? Price equal to the MA line MUST NOT be treated as "above" it — the
  rule only blocks when price is strictly above the line by more than the
  allowed margin.
- This rule applies only to decisions about opening a **new** long position;
  it MUST NOT affect SHORT entries, and MUST NOT affect management of
  positions that are already open.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST compare the current price against a configured
  moving-average reference line every time it evaluates whether to open a new
  long position.
- **FR-002**: The system MUST NOT open a new long position when the current
  price is above the configured moving-average reference line by more than
  the allowed margin: [NEEDS CLARIFICATION: which moving-average line is "the
  MA signal" — the fast line (MA7), the mid line (MA25), or the slow line
  (MA99)?]
- **FR-003**: The margin that separates "acceptably near the line" from
  "too far above the line" MUST be configurable or otherwise well-defined,
  rather than blocking on any distance above the line at all: [NEEDS
  CLARIFICATION: should the block trigger the instant price is above the
  line at all (zero margin), or only once price exceeds the line by a defined
  buffer? If a buffer, what is it — e.g., a fixed percentage, or a multiple of
  current volatility?]
- **FR-004**: When a long entry is skipped because of this rule, the system
  MUST record a human-readable reason that references the moving-average
  condition, visible to the operator through the existing trade/decision log.
- **FR-005**: This rule MUST NOT change how SHORT positions are evaluated or
  opened.
- **FR-006**: This rule MUST NOT affect the management (partial exits, stop
  moves, closing) of long positions that are already open at the time the
  rule would otherwise trigger.
- **FR-007**: This rule MUST apply consistently across every path that can
  open a new long position, so an operator cannot end up chasing an extended
  move through one entry path while it is correctly blocked on another.

### Key Entities

- **Long Entry Evaluation**: The point in time where the bot decides whether
  to open a new long position for a symbol; considers the current price and
  the relevant moving-average reference value.
- **Skipped Entry Reason**: A record explaining why a long-entry opportunity
  did not result in an order, including the fact that price was too far above
  the moving-average reference line.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Across a full backtest or paper-trading run, zero new long
  positions open on a candle where price closed above the configured
  moving-average reference line by more than the allowed margin.
- **SC-002**: For every long-entry opportunity skipped because of this rule,
  the operator can find a corresponding log entry explaining the skip within
  the existing logs/trade history view.
- **SC-003**: Long-entry opportunities that satisfy all existing conditions
  and stay within the allowed margin of the moving-average reference line
  continue to open at the same rate as before this change (no regression).

## Assumptions

- The "MA signal" referenced by the operator is one of the moving-average
  lines already used by the bot's trend and entry logic; this spec assumes it
  is a single, well-defined line rather than a new indicator, pending the
  clarification above.
- This rule is an additional restriction layered on top of existing long-entry
  conditions — it can only prevent a long entry that would otherwise have been
  taken; it does not by itself allow any entry that current logic would
  reject.
- "Already open positions" are entirely out of scope: this feature only gates
  the decision to open a brand-new long position.
