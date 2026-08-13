---
status: draft
source: founder interview 2026-08-11 (B-0006 §11)
blocked_by: B-0028
---

# 11 — Comms

**Draft.** Question 11.1 — which notifications are real-time and which run on a
cadence — is answered: see "The routing table" below (B-0013 → D-031). Structure,
privacy and routing are settled. The chapter stays draft on one remaining gap:
the routing table says *cadence* for seven of the eight message kinds without
saying *what cadence* — **B-0028**. SPEC-COM cannot write an AC against "batched"
alone, so that number is the last thing between this chapter and authoritative.

Discord is the single staff channel (D-018). Nobody is on it yet, so every
decision below is also a rollout decision.

## Topology

Roles and channels mirror the org chart, so permissions fall out of it rather
than being maintained separately.

- A **category per territory**, a **channel per store** inside it.
- **A channel per field manager, for their territory** (11.5A).
- Store managers see **their own store only** — not peer stores.

Peer visibility was considered and declined. It would let managers compare
directly, and it would also mean every store's problems are visible to fourteen
other managers. The territory channel is where cross-store conversation happens,
with the FM present.

Roles: `owner` · `field_manager` · `store_manager` · `office` · `crew`, plus a
per-store role. A crew member at Kent holds `crew` and `store-38699`, and sees
exactly the Kent channel and org-wide channels.

## Personal by DM, store business in channel

**Personal things go by DM; store things go in the store channel** (11.2A).

DM: shifts, schedule changes, training assignments, certificate expiry, points
balance, personal recognition.

Channel: yesterday's store numbers, task of the week, recognition posts naming
winners, anything the whole store acts on.

The test is whether the message is *about* one person or *for* the store.

## Crew can post

**Everyone in a store can post in their store channel** (11.3A). It is a working
channel, not a noticeboard.

This is the decision that makes Discord worth adopting rather than a broadcast
tool that could have been SMS — shift swap requests, "the slicer is jammed",
handover notes. It also means moderation is real: the channel carries whatever
people type, and the privacy boundary below is a rule people can break, not just
a rule the bot follows.

## The privacy boundary

**Never in Discord, in any channel or DM** (11.4, confirmed):

- wages and pay rates
- individual bonus amounts and gift card values
- disciplinary matters
- anything from an employee's certificate or records file

Discord is a third party. Anything sent there has left the system's control, is
retained on someone else's servers, and is visible to whoever holds the account.

Two consequences that are easy to get wrong:

- **Bonus standings are attainment percentages and rank, never dollars** — see
  [05-COMPENSATION](../05-COMPENSATION/README.md).
- **Certificate expiry nudges say *that* something expires, never what it
  contains.** "Your food handler card expires in 30 days — open your page to
  renew" is the whole message. The document itself lives behind an authenticated,
  signed, short-lived URL per
  [07-SAFETY-HEALTH-AND-RECORDS](../07-SAFETY-HEALTH-AND-RECORDS/README.md).

The general rule: **Discord carries notification, the app carries content.** A
message may say something needs attention and link to the page. It does not
reproduce the page.

## Rollout

Nobody is on Discord today, so adoption is the risk, not the code. Pilot one
territory — Lauren's three stores (10393, 24339, 26999) — before org-wide.

Three stores is enough to learn whether crew actually read it, and small enough
that abandoning it costs nothing.

## The routing table

Settled by B-0013 → **D-031**. One message kind is real-time. Every other kind
batches.

| Message kind | Routing |
|---|---|
| Shift reminders | **real-time** |
| Yesterday's numbers | cadence |
| Schedule publication | cadence |
| Overtime notifications | cadence |
| Task assignment | cadence |
| Bonus standings | cadence |
| Reconciliation exceptions | cadence |
| Certificate expiry | cadence |

**Why only shift reminders.** A shift reminder is the one message whose value
expires — it is useless after the shift starts, and it is addressed to someone
who has not yet acted. Everything else on the list reports something that has
already happened, and reporting it four hours sooner changes nobody's behavior.
Per [08-SCHEDULING-AND-HOURS](../08-SCHEDULING-AND-HOURS/README.md), overtime is
now detection rather than prediction, so even the overtime message describes a
threshold already crossed.

**The reasoning that actually decided it was volume, not technology.** A system
that pushes eight kinds of message in real time trains everyone to mute the
channel, and a muted channel is worse than no channel — it looks like
communication while carrying none. Real-time is a budget, and it is spent.

**Consequence for every future capability.** A new notification is *cadence* by
default. Promoting one to real-time spends from a budget that currently has one
occupant, so it is a founder decision recorded here, not a spec-level choice.

**What is still open.** "Cadence" is not yet a number. Which of the seven batch
daily, which weekly, and at what local hour — that is **B-0028**, and it is what
keeps this chapter draft.
