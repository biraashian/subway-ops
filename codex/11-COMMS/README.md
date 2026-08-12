---
status: draft
source: founder interview 2026-08-11 (B-0006 §11)
blocked_by: B-0013
---

# 11 — Comms

**Draft.** Question 11.1 — which notifications are real-time and which run on a
cadence — was not answered. It is the routing table the whole comms layer reads,
so no spec anchors here until B-0013 resolves. Structure and privacy are
settled.

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

## What B-0013 needs to settle

Which of these are real-time, and which run on a cadence:

yesterday's numbers · schedule publication · shift reminders · overtime
notifications · task assignment · bonus standings · reconciliation exceptions ·
certificate expiry.

The proposal offered and not adopted: only shift reminders are real-time, and
everything else is cadence — noting that per
[08-SCHEDULING-AND-HOURS](../08-SCHEDULING-AND-HOURS/README.md) overtime is now
detection rather than prediction, so an overtime message reports something that
already happened and has no urgency to preserve.

The thing that actually needs deciding is not the technology but the volume. A
system that pushes eight kinds of message in real time trains everyone to mute
the channel, and a muted channel is worse than no channel — it looks like
communication while carrying none.
