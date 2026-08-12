---
status: authoritative
source: harvested from the pre-Burst CLAUDE.md, playbook §5, and the 2026-05-11 decision
---

# 01 — The Business Calendar

Load-bearing. Almost every defect that looks like "the numbers are off by one
day" is this chapter being ignored somewhere.

## The two definitions

1. **A business day runs 02:00 local → 01:59 the next calendar day, local.**
   A sale rung at 00:30 on Tuesday belongs to Monday's business date. Stores
   close after midnight; the cutoff exists so a single closing shift is not
   split across two days.

2. **A business week runs Wednesday → Tuesday.** It opens at Wednesday 02:00
   wall clock and closes at 01:59 the following Wednesday. Week-end dates are
   therefore always Tuesdays, and "last week" means the most recently *closed*
   Wed–Tue pair, never the last seven days.

Wednesday is also why the digest lands Wednesday morning: the week has just
closed and the numbers are final.

## Timezone

All 15 stores are in WA and OR, so the system assumes a single timezone,
`America/Los_Angeles`, and `ref_stores.timezone` carries it explicitly for every
row.

The column exists so that the assumption is *data* rather than a hardcoded
constant — the day a store opens outside Pacific time, this becomes per-store
and the schema already supports it. Do not add a second hardcoded timezone
anywhere; read the column.

Note the trap this column has already sprung once: a malformed seed row put
`timezone = 'October 18, 2023'` into `ref_stores` and nothing noticed for three
months. `tools/verify_invariants/check_seed_wellformed.py` exists because of it.

## Trust the API

The Fresh Connect API is already business-date aligned. Two facts, both
verified in the Task 1.3 discovery pass against live payloads:

- The `date` field on daily endpoints **is** the business date. Trust it. Do not
  re-derive it from a timestamp.
- The `weekEndDate` parameter and field **is** always a Tuesday. Trust it.

Re-deriving either is how a system ends up with two disagreeing notions of
"Monday" and no way to tell which is right.

## Helpers

`src/subway_ops/calendar.py` is the only place these rules are implemented. Use
it everywhere; never inline a `timedelta(days=7)` and call it a week.

| Function | Returns |
|---|---|
| `business_date_now(now=None)` | the business date right now |
| `dt_to_business_date(dt)` | a wall-clock timestamp's business date |
| `business_week_of(d)` | `(wednesday_start, tuesday_end)` containing `d` |
| `previous_business_week(today=None)` | the most recently closed Wed–Tue pair |
| `is_business_week_end(d)` | whether `d` is a Tuesday |

A test fixture that hardcodes a date instead of deriving it from these helpers
will rot. That is not hypothetical: `test_mart_recon_weekly.py` pinned
`WEEK_END = date(2026, 5, 5)` while the code under test computed its window from
today, and every assertion in the file had been failing silently for two months
before anyone ran the suite. **Derive test dates from the calendar.**

## DST and cron

GitHub Actions crons are UTC and have no calendar awareness, so the wall-clock
arrival time of every scheduled job shifts by an hour twice a year. The
Wednesday digest fires at `0 14 * * 3`, landing 07:00 PT in winter and 06:00 PT
in summer.

**This drift is accepted** (decision dated 2026-05-13). The digest is a leisurely
weekly read, not a time-critical alert; the Wednesday placement is the
load-bearing part, not the hour. Revisit only if a job becomes tied to a specific
shift handoff — at which point the fix is a worker that wakes daily and
self-schedules through `subway_ops.calendar`, not a cleverer cron expression.

Anything that *is* time-critical — an overtime warning that must arrive before a
shift starts — cannot rely on a UTC cron and must state its timing requirement
in its own spec.
