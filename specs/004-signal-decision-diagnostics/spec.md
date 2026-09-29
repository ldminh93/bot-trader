# Feature Specification: Signal Decision Ledger & Trade Diagnostics

**Feature Branch**: `004-signal-decision-diagnostics`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "Signal decision ledger and trade diagnostics. Record every entry decision the bot makes each cycle (taken and rejected), fill in forward outcomes later, add R-multiple / MFE / MAE to trades, and add a Diagnostics page showing per-gate value, score/grade calibration, R and expectancy by tag and regime x side, and exit-quality summary. Read-only for existing trading behavior, paper-first safe, scoped per user."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See whether each entry gate earns its keep (Priority: P1)

As a trader tuning my bot, I want every entry decision (taken or rejected) recorded together with what the market did afterwards, so I can tell whether a gate (e.g. extended-move, pullback location, RSI, funding, circuit breaker) blocks losers or blocks winners.

**Why this priority**: Gate thresholds are currently tuned by feel; rejections only exist as free-text log lines with no outcome. This is the most direct evidence for deciding what to tighten, loosen or remove.

**Independent Test**: Run a bot (paper) for several cycles with at least one gate firing, wait for the follow-up windows to elapse, then open the Diagnostics page and confirm the gate shows a blocked count and a would-have-won / would-have-lost split.

**Acceptance Scenarios**:

1. **Given** a running bot evaluates a symbol and a gate rejects the candidate, **When** the cycle completes, **Then** a decision record exists with the symbol, candidate side, score/confidence/grade, regime, the blocking gate's name and the price at decision time.
2. **Given** the bot opens a trade, **When** the cycle completes, **Then** a decision record marked "taken" exists linked to that trade.
3. **Given** a rejected decision older than 1 hour, **When** the follow-up job runs, **Then** the record shows the best and worst price move since the decision and whether the would-be stop-loss or first take-profit would have been reached first (or neither yet).
4. **Given** the same follow-up at 4 hours and 24 hours, **When** each window elapses, **Then** those outcomes are filled in without altering earlier ones.

---

### User Story 2 - Measure trades in R with excursion data (Priority: P1)

As a trader, I want each trade to carry its R-multiple and its maximum favorable and adverse excursion, so I can judge trade quality independent of position size.

**Why this priority**: Win rate and USDT PnL alone hide whether stops are too tight or profits are given back; R/MFE/MAE are the raw inputs for all exit-quality analysis.

**Independent Test**: Open a paper trade, let price move in both directions across several cycles, close it, and confirm the recorded R-multiple, MFE and MAE match the price path and initial stop distance.

**Acceptance Scenarios**:

1. **Given** an open trade, **When** each bot cycle runs, **Then** its best and worst excursion since entry (in price percent and in R) are updated if exceeded.
2. **Given** a trade closes, **When** the close is recorded, **Then** its final R-multiple (realized PnL relative to the initial risk) and final MFE/MAE are stored.
3. **Given** a historical closed trade with no excursion data, **When** diagnostics are viewed, **Then** R is derived from stored data where possible and MFE/MAE are shown as unavailable rather than zero.

---

### User Story 3 - Diagnostics page for calibration and expectancy (Priority: P2)

As a trader, I want one Diagnostics page that summarizes gate value, score/grade calibration, expectancy by setup tag and by regime × side, and exit quality, so I can see what to change without querying data by hand.

**Why this priority**: Turns the recorded data of Stories 1–2 into decisions; depends on them.

**Independent Test**: With a mix of taken/rejected decisions and closed trades, open the page and verify each of the four sections renders correct figures and flags small samples.

**Acceptance Scenarios**:

1. **Given** rejected decisions with outcomes, **When** I view "Gate value", **Then** for each gate I see blocked count, % that would have won, % that would have lost, % undecided, and net R (R saved by blocking losers minus R missed by blocking winners).
2. **Given** closed trades with score and grade, **When** I view "Calibration", **Then** I see trade count, win rate and average R per score bucket and per grade, so I can check that higher scores actually perform better.
3. **Given** closed trades with setup tags and regimes, **When** I view "Expectancy", **Then** each tag and each regime × side row shows trades, win rate, average R and expectancy, and any row with fewer than 30 trades is visibly flagged as low-sample.
4. **Given** trades with excursion data, **When** I view "Exit quality", **Then** I see average give-back from peak (MFE minus realized R), the share of stopped-out trades that had first been meaningfully in profit (+0.5R), and how much adverse excursion winners endured versus how far losers went in favor first — evidence on whether stops are too tight or profits are given back.
5. **Given** a date range and paper/live filter, **When** I change them, **Then** all sections update consistently.

---

### Edge Cases

- A gate fires for the same symbol every cycle: repeated rejections by the same gate for the same symbol and side within one signal candle are recorded once, so storage does not explode and counts are not inflated.
- Price data for a follow-up window is unavailable (exchange outage): the outcome stays "pending" and is retried; it is never guessed.
- Both stop-loss and first take-profit are touched inside one follow-up interval: ordering is unknowable, so the outcome is marked "ambiguous" and excluded from win/loss percentages.
- A decision has no computable stop/TP (rejected before risk planning): a stated default risk distance is used, or the record is marked "no reference levels" and excluded from R totals.
- Trade with zero or missing initial stop: R is unavailable, not infinite.
- Trade closed before excursion tracking existed: MFE/MAE unavailable.
- User has no data yet: page shows an explanatory empty state, not zeros.
- Recording or follow-up jobs fail: the trading cycle continues unaffected; diagnostics never block or delay entries/exits.
- Data volume growth: old decision records are pruned after a retention window.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST record one decision per bot cycle per evaluated symbol/side candidate, whether rejected or taken, including timestamp, owning user, bot configuration, symbol, candidate side, score, confidence, grade, regime, decision result ("taken" or the specific blocking gate identifier) and price at decision time.
- **FR-002**: System MUST link a "taken" decision to the resulting trade.
- **FR-003**: System MUST use a stable, enumerable gate identifier for every existing rejection path (not free text) so results can be grouped.
- **FR-004**: System MUST fill in forward outcomes for each decision at 1 hour, 4 hours and 24 hours after the decision: maximum favorable move, maximum adverse move, and which of would-be stop-loss / first take-profit was reached first (or neither / ambiguous).
- **FR-005**: System MUST leave outcomes "pending" when market data is unavailable and retry later; it MUST NOT fabricate values.
- **FR-006**: System MUST track each open trade's maximum favorable and adverse excursion (percent and R) every bot cycle and finalize them on close.
- **FR-007**: System MUST store each closed trade's R-multiple, computed from realized PnL relative to initial risk (initial stop-loss), and treat missing/zero initial risk as "unavailable".
- **FR-008**: System MUST NOT change any entry, exit, sizing, or gating behavior; recording and analysis failures MUST NOT interrupt a bot cycle.
- **FR-009**: System MUST provide a Diagnostics view with four sections: gate value, score/grade calibration, expectancy by setup tag and by regime × side, and exit quality (as defined in User Story 3).
- **FR-010**: Every aggregated row MUST show its sample size, and rows with fewer than 30 trades/decisions MUST be flagged as low-sample.
- **FR-011**: Diagnostics MUST be filterable by date range and by paper vs live trades.
- **FR-012**: All recorded data and diagnostics MUST be scoped to the requesting user; one user must never see another's decisions or trades.
- **FR-013**: System MUST distinguish paper and live trades in stored data and aggregation; paper-mode behavior MUST be identical to before.
- **FR-014**: System MUST prune decision records older than a retention window (default 90 days) while retaining R/MFE/MAE on the trade itself.
- **FR-015**: System MUST show a clear empty state when there is insufficient data.

### Key Entities

- **Signal Decision**: One evaluation of a symbol/side candidate in a bot cycle. Attributes: user, bot config, symbol, side, score, confidence, grade, regime, result (taken / gate identifier), decision price, reference stop/TP levels, linked trade (if taken), and three forward-outcome sets (1h, 4h, 24h), each holding max favorable move, max adverse move, first-level-reached and status.
- **Trade (extended)**: Existing trade record plus R-multiple, maximum favorable excursion and maximum adverse excursion.
- **Diagnostics Summary**: Read-only aggregate view (not stored) built from decisions and trades for one user and filter.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of bot cycles that evaluate a candidate produce a decision record identifying either "taken" or a specific gate (no free-text-only rejections).
- **SC-002**: At least 95% of decisions have all three follow-up outcomes filled within 30 minutes after their window elapses, when market data is available.
- **SC-003**: For 100% of closed trades with a valid initial stop, R-multiple, MFE and MAE are available and reproducible from the trade's price path in spot checks.
- **SC-004**: A trader can identify, within 2 minutes of opening the page, which gate has the largest net R saved or missed.
- **SC-005**: The Diagnostics page loads in under 3 seconds for a user with 10,000 decisions and 1,000 trades.
- **SC-006**: Bot cycle behavior and trade results are unchanged versus before the feature (existing trading tests still pass).
- **SC-007**: Zero cross-user data exposure in access tests.

## Assumptions

- Extends the existing trading app; no new external services. Follows the constitution: paper-first safety, test-first for new logic, graceful degradation.
- Follow-up outcomes use exchange candle history at a finer resolution than the signal timeframe; "would-be" stop/TP use the levels the risk planner would have produced, else a stated default risk distance.
- "Would have won" means the first take-profit was reached before the stop within the window; "would have lost" the reverse.
- Score buckets are 10-point bands; the low-sample threshold is 30.
- Retention default is 90 days for decision records.
- Historical trades are not backfilled for MFE/MAE; R is derived where initial stop data exists.
- Users see only their own diagnostics; no cross-user aggregate view in this feature.
- Out of scope: automatic threshold tuning, changing any gate, config versioning, slippage/fee breakdown.
