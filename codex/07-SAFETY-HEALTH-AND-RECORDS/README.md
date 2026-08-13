---
status: authoritative
source: founder interview 2026-08-11 (B-0006 §7)
---

# 07 — Safety, Health and Records

This chapter has legal weight. Where it states a retention period or a required
record, a spec pins behaviour to it directly.

## What must exist per employee

| Record | Kind | Renews |
|---|---|---|
| WA / OR food handler card | credential | yes — card expiry |
| Safety orientation | attestation | annually |
| Health / hygiene orientation | attestation | annually |
| Harassment training | attestation | annually |
| **I-9** | employment eligibility | no — see below |
| **W-4** | tax withholding | on change |

Each is a row against the **person**, not an assignment — a food handler card
does not stop being valid because someone picked up a shift at another store.

## I-9 and W-4 are in scope, under their own rules (B-0010 → B)

Decided 2026-08-13. They are held here, **not** by payroll. But they are not
just two more credential rows, and modelling them that way would get two things
wrong at once.

**The I-9 has its own retention rule.** Three years after the hire date, or one
year after termination, whichever is **later** — not the seven years below. For
a long-tenured employee that is *shorter* than seven years; for someone who
left after six months it is *longer* than one. A single retention constant
cannot express it, so the record type carries its own rule and the renewal
machinery computes from both dates.

**The I-9 must be stored separately from the personnel file.** The reason is
practical: an I-9 audit is entitled to see I-9s and nothing else. If they sit
in the same store as food handler cards and training records, producing the
I-9s means either exposing the rest or doing manual extraction under time
pressure. A separate bucket with its own access rule makes the audit response a
query rather than a scramble.

The same separation applies to the W-4, which carries a Social Security number
— the single most sensitive field in this system. **A W-4 is never rendered in
any list, export, packet or notification.** It is retrievable individually, by
office and owner only, and every retrieval is logged.

Neither appears in the inspection packet below. A health inspector has no claim
on either, and a packet that included them would hand over more than was
asked.

## Retention: 7 years

**Seven years after termination** (7.2) — applied to every record type above
**except the I-9**, which follows the later-of rule stated in its own section.

Records are retained, never deleted, per
[06-PEOPLE](../06-PEOPLE/README.md). Nothing in the current design purges at
seven years — the period is the *minimum* the system guarantees, and an
automated purge is not built. If purge-on-schedule is ever wanted it is its own
spec, because deleting compliance records on a timer is not something to do as a
side effect.

## Who may see an employee's records

The employee · their store manager · their **field manager** · office · the
owner (7.3, A and B).

**Except I-9 and W-4: office and owner only.** A store manager has no reason to
see an employment-eligibility document or a Social Security number, and the
narrower rule costs nothing because neither is needed to run a shift.

Not other crew. Not `readonly` — the mentor/lender view sees no personally
identifying employee data at all, per
[00-INSTITUTION](../00-INSTITUTION/README.md).

Enforcement is server-side on every query. A certificate is a file in object
storage; access goes through a signed, short-lived URL issued only after the
same check — never a public bucket path, because a leaked URL to a food handler
card is a leaked identity document.

## Expiry and renewal

Every credential and attestation carries an expiry: the card's own date for
credentials, `completed_at + renewal_months` for annual attestations.

**Nudges at 60, 30 and 7 days** (7.5). Each nudge is a worklist item, not just a
notification — a notification is dismissed and forgotten, a worklist item stays
open until someone resolves it.

An **expired** credential is a distinct state from an expiring one and escalates:
the employee, their store manager, and office all see it, and the person shows
as non-compliant in the inspection packet below.

The same expiry machinery serves store-level renewals — business licenses,
health permits, hood cleaning, backflow tests, pest contracts, insurance. These
attach to a store rather than a person; the mechanism is identical and should
not be built twice.

## The inspection packet

One tap, one store, one timestamped PDF (7.4):

- every **currently active** employee's food handler card, with expiry and a
  clear valid / expiring / expired state
- their training and orientation completions with dates
- store-level permits
- the pest control log

The packet is generated on demand and stamped with the moment it was produced,
because it is a point-in-time assertion. It is never cached and re-served — an
inspector holding a packet that says "as of today" must be holding today's
truth.

Terminated employees are excluded from the packet but remain retrievable
individually, since the retention period exists precisely so that a question
about a former employee can be answered.

The packet is the moment this system earns its keep: an inspector is standing in
the store, and the alternative is a binder in the back office that may or may
not be current.
