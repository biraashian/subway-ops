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

Each is a row against the **person**, not an assignment — a food handler card
does not stop being valid because someone picked up a shift at another store.

**I-9 and W-4 are excluded pending B-0010.** They were in the interview's
starting list, answered "everything you said", but the list itself flagged them
as probably belonging to payroll rather than here — so the answer is genuinely
ambiguous and this chapter does not resolve it.

The reason it matters rather than being pedantry: an I-9 has its own federal
retention rule (three years after hire or one year after termination, whichever
is later — *not* the seven years below), and it is conventionally stored
**separately** from the personnel file so that an audit of I-9s does not expose
everything else. Building it as just another credential row would get both
wrong. It stays out until decided.

## Retention: 7 years

**Seven years after termination** (7.2), applied uniformly to the record types
above.

Records are retained, never deleted, per
[06-PEOPLE](../06-PEOPLE/README.md). Nothing in the current design purges at
seven years — the period is the *minimum* the system guarantees, and an
automated purge is not built. If purge-on-schedule is ever wanted it is its own
spec, because deleting compliance records on a timer is not something to do as a
side effect.

## Who may see an employee's records

The employee · their store manager · their **field manager** · office · the
owner (7.3, A and B).

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
