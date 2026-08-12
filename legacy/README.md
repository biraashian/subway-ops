# legacy/ — retired, read-only

These documents governed the pre-Burst build. They are **no longer
authoritative**. Where they disagree with a chapter in `codex/`, the codex wins.

They are kept, not deleted, because they are the record of why the data layer
looks the way it does, and because the codex harvests from them — a retro-spec
(D-016) reads them for prior art and presents what they chose as a labeled
option, never as a settled answer.

| Document | Superseded by |
|---|---|
| `SUBWAY_OPS_BUILD_PLAYBOOK.md` | `codex/` chapters 00–02 and 13, plus the spec layer |
| `SUBWAY_OPS_TASKS.md` | `workshop/WORKSHOP.md` and `chronicle/CHRONICLE.md` |

The pre-Burst `CLAUDE.md` is not here as a file — it was rewritten in place as
Burst law. Its previous contents are in git history at `4b499e2:CLAUDE.md`, and
its domain half now lives in `codex/00`, `codex/01`, `codex/02` and `codex/13`.

The dated decision log from that era is preserved verbatim at the bottom of
`DECISIONS.md` rather than moved here, because `/sweep` diffs live state against
that file and splitting it would hide half the history from the check.

## A caution about the task tracker

`SUBWAY_OPS_TASKS.md` marks every task `[~]` complete, including a 12-month
backfill that had not been run when it was written and an audit whose findings
were three months stale by the time anyone re-read them. It is a record of what
was *intended*, not of what was *true*. Do not cite it as evidence that anything
works. That is what `journal/`, `test_logs/` and the gate are for.
