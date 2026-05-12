# Architectural decisions

Append-only log of significant design choices. Each entry: context,
decision, consequences. Newest at the bottom.

---

## 2026-05-11 — Language and stack

**Context:** Operator preference for Python; need free-tier-only hosting;
need declarative dashboards.

**Decision:** Python 3.12, Streamlit, Supabase Postgres, GitHub Actions
for orchestration.

**Consequences:** Locked into Python ecosystem; Streamlit's auth
limitations accepted; daily-batch architecture rather than real-time.

---

## 2026-05-11 — Business calendar

**Context:** Subway operates on a non-midnight day boundary and a
non-Monday week boundary. Every downstream KPI rolls up by business
date or business week, so the definition has to be unambiguous and
codified in one place.

**Decision:** Business day is 02:00–01:59 local (America/Los_Angeles for
all 15 stores). Business week is Wednesday through Tuesday. The Fresh
Connect API's `date` field is already business-date-aligned and its
`weekEndDate` is always a Tuesday; both are trusted and not re-derived.

**Consequences:** All calendar logic flows through `subway_ops.calendar`.
Any time we compute "today" or "this week" for reporting, we do it via
those helpers, never via `datetime.date.today()`. If a future store opens
outside America/Los_Angeles, the timezone assumption must be revisited.

---

## 2026-05-11 — Bank reconciliation model

**Context:** 15 stores deposit to multiple banks; building per-bank CSV
parsers exceeds the value of the variance signal at our current scale.

**Decision:** We do not ingest bank-issued deposit confirmations. The
dashboard surfaces the POS-recorded `depositInBank` from ControlSheet. A
variance entry form exists for operators to record actual bank-deposited
amounts only when they differ from the POS-recorded amount.

**Consequences:** We catch over/short via human-in-the-loop, not
automation. Acceptable for v1; revisit if variance frequency grows or if
we onboard a single banking partner that makes automated reconciliation
cheap.
