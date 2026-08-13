#!/usr/bin/env bash
# verify.sh — the Subway Ops verification sweep (Gate 1)
# Usage:  ./scripts/verify.sh T-XXXX [pre-merge|post-merge|adhoc]
#
# Logs to: test_logs/T-XXXX/T-XXXX-<phase>.md   (append-only per phase, gitignored)
# Exit:    0 if no failures, 1 if any check failed.
#          Missing optional tools are warnings, not failures.
#
# ---------------------------------------------------------------------------
# PHASES
#
#   adhoc       fast inner loop. Tests, types, lint, invariants.
#   pre-merge   the gate. Everything, plus the schema snapshot, drift against
#               the baseline, codex consistency, and evidence presence
#               (the journal entry and its declared decisions).
#   post-merge  confirm the merge is clean on the integration branch, then
#               ROTATE THE BASELINE: the schema captured here becomes
#               .drift/schema-before.json for the next task.
#
# That rotation is what gives the NEXT task's drift check a --before to point
# at. It is not a separate step anyone has to remember.
#
# ---------------------------------------------------------------------------
# LOG FORMAT
#
# One directory per task, one file per phase, so a fast adhoc loop never
# buries the pre-merge gate record. Each run appends a block that leads with
# a verdict line and a scannable results table; full output lives inside
# collapsed <details> sections. Failed checks are written EXPANDED so a red
# run shows its own evidence without a click.
# ---------------------------------------------------------------------------

set +e  # run every check; never abort on first red

TASK_ID="${1:?Usage: verify.sh T-XXXX [pre-merge|post-merge|adhoc]}"
SWEEP_RAW="${2:-adhoc}"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

# ---- repo-local tooling (override via env) --------------------------------
# Everything this gate needs lives in the repo. The Verity edition reached out
# to $AASHIAN for a module registry, a contract-drift checker and a codex; this
# domain's contract is its DATABASE SCHEMA, so the drift analogue is a schema
# snapshot and the rest is a set of invariant checks over the repo itself.
REPO_ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SCHEMA_SNAPSHOT="${SCHEMA_SNAPSHOT:-$REPO_ROOT_DIR/scripts/schema_snapshot.py}"
INVARIANTS_DIR="${INVARIANTS_DIR:-$REPO_ROOT_DIR/tools/verify_invariants}"
CODEX_ROOT="${CODEX_ROOT:-$REPO_ROOT_DIR/codex}"

# Everything runs through uv — this project has no activated-venv workflow.
RUN="${RUN:-uv run}"

# .drift/ lives in the MAIN repo. `--show-toplevel` returns the WORKTREE root
# when run from a worktree, which silently points the baseline somewhere it
# does not exist. `--path-format=absolute --git-common-dir` returns the shared
# .git of the main repo from anywhere, including inside a worktree.
_GIT_COMMON="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"
DRIFT_DIR="${DRIFT_DIR:-$(dirname "${_GIT_COMMON:-.}")/.drift}"
SCHEMA_OUT="${SCHEMA_OUT:-$DRIFT_DIR/schema-now.json}"
BASELINE="$DRIFT_DIR/schema-before.json"

# The journal is IN this repo (D-023, amending D-003) — one clone carries the
# whole record. Because it is in-repo, the worktree-clean assertion would see
# the entry written moments before the gate runs, so that assertion excludes
# `journal/` and `test_logs/` and nothing else.
JOURNAL_DIR="${JOURNAL_DIR:-$REPO_ROOT_DIR/journal}"
DECISIONS_FILE="${DECISIONS_FILE:-$REPO_ROOT_DIR/DECISIONS.md}"
INTEGRATION_BRANCH="${INTEGRATION_BRANCH:-}"
MAX_LOG_LINES="${MAX_LOG_LINES:-120}"   # per-check output cap in the log

# ---- normalise the phase --------------------------------------------------
case "$SWEEP_RAW" in
    pre-merge|premerge|pre)    SWEEP="pre-merge" ;;
    post-merge|postmerge|post) SWEEP="post-merge" ;;
    adhoc|ad-hoc|"")           SWEEP="adhoc" ;;
    *) echo "ERROR: unknown sweep '$SWEEP_RAW' (pre-merge|post-merge|adhoc)" >&2; exit 2 ;;
esac

in_phase() { local p; for p in "$@"; do [[ "$SWEEP" == "$p" ]] && return 0; done; return 1; }

# ---- log location: one dir per task, one file per phase -------------------
LOG_ROOT="${LOG_ROOT:-$REPO_ROOT_DIR/test_logs}"
LOG_DIR="$LOG_ROOT/$TASK_ID"
LOG_FILE="$LOG_DIR/${TASK_ID}-${SWEEP}.md"
mkdir -p "$LOG_DIR"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: not inside a git repo. cd to the subway-ops checkout first." >&2
    exit 2
fi
if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv not on PATH. This project's toolchain is uv; see README." >&2
    exit 2
fi

BRANCH="$(git branch --show-current)"
COMMIT="$(git rev-parse --short HEAD)"
REPO="$(basename "$(git rev-parse --show-toplevel)")"
WORKTREE="$(git rev-parse --show-toplevel)"

SCRIPT_PATH="${BASH_SOURCE[0]}"
# Identity is the CONTENT, not the history. `git log -1 -- <path>` applies
# history simplification: when the same script lands on two branch lines it
# reports whichever commit the simplified walk attributes the path to, which
# is not the same question as "which version ran". The blob is exact and
# stable under merges; the commit is kept as secondary context.
SCRIPT_BLOB="$(git hash-object "$SCRIPT_PATH" 2>/dev/null || echo unknown)"
SCRIPT_COMMIT="$(git log -1 --format=%h -- "$SCRIPT_PATH" 2>/dev/null || echo unknown)"
SCRIPT_DIRTY=""
# Against HEAD, not the index: `git diff --quiet -- <path>` compares worktree
# to index, so a STAGED edit to this script reports clean — and staged is
# exactly how a modified gate rides along through a checkout.
# Untracked is checked FIRST and separately. `git diff HEAD -- <path>` reports
# no difference for a file git has never seen, so an untracked gate script -- a
# strictly worse state than a modified one, since there is no committed version
# to compare against at all -- was being reported as clean.
if ! git ls-files --error-unmatch "$SCRIPT_PATH" >/dev/null 2>&1; then
    SCRIPT_DIRTY=" ⚠️ UNTRACKED — this gate is not in version control"
elif ! git diff --quiet HEAD -- "$SCRIPT_PATH" 2>/dev/null; then
    SCRIPT_DIRTY=" ⚠️ UNCOMMITTED"
fi

if [[ -z "$INTEGRATION_BRANCH" ]]; then
    for cand in master main forge/reconstruction; do
        if git show-ref --verify --quiet "refs/heads/$cand"; then INTEGRATION_BRANCH="$cand"; break; fi
    done
fi

# ---- scratch buffers: the summary table must precede the detail blocks,
#      but both are produced as checks run, so assemble at the end ----------
TMP="$(mktemp -d -t verify-XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
ROWS="$TMP/rows.md"; BLOCKS="$TMP/blocks.md"; : > "$ROWS"; : > "$BLOCKS"

failures=(); warnings=(); skipped_phase=(); passes=0
RUN_START=$(date +%s)

# ---------------------------------------------------------------------------
# headline <label> <output>
#   Extract the one line worth putting in the summary table. A results table
#   that just says "pass" 14 times is a table nobody reads; "2806 passed,
#   4 skipped" is worth the column.
# ---------------------------------------------------------------------------
headline() {
    local label="$1" out="$2" h=""
    case "$label" in
        "Test discovery")   h=$(grep -oE '[0-9]+ tests? collected[^ ]*( in [0-9.]+s)?' <<< "$out" | tail -1) ;;
        "Full regression")  h=$(grep -oE '[0-9]+ (passed|failed)[^=]*' <<< "$out" | tail -1) ;;
        "Coverage")         h=$(grep -oE 'TOTAL +[0-9]+ +[0-9]+ +[0-9]+%' <<< "$out" | tail -1 \
                                 | awk '{print "total coverage " $4}')
                            [[ -z "$h" ]] && h=$(grep -oE '[0-9]+ passed[^=]*' <<< "$out" | tail -1) ;;
        "mypy --strict")    h=$(grep -oE 'Success: no issues found in [0-9]+ source files|Found [0-9]+ errors?' <<< "$out" | tail -1) ;;
        "ruff check")       h=$(grep -oE 'All checks passed!|Found [0-9]+ error' <<< "$out" | tail -1) ;;
        "invariants")       h=$(grep -oE '[0-9]+ passed, [0-9]+ failed' <<< "$out" | tail -1) ;;
        "schema snapshot")  h=$(grep -oE '[0-9]+ tables?, [0-9]+ columns?' <<< "$out" | tail -1) ;;
        "schema drift")     h=$(grep -oE 'no drift|drift matches declaration \([0-9]+ change\(s\), all declared\)|[0-9]+ UNDECLARED change\(s\)|[0-9]+ STALE declaration line\(s\)|[0-9]+ change\(s\)' <<< "$out" | head -2 | paste -sd' · ' -) ;;
        "drift_check.py")   h=$(grep -oE 'GREEN|RED|[0-9]+ errors?, [0-9]+ warnings?' <<< "$out" | tr '\n' ' ') ;;
        "verify-codex.sh (15 checks)")
                            h=$(grep -oE 'Passed: [0-9]+' <<< "$out" | tail -1)
                            local f; f=$(grep -oE 'Failed: [0-9]+' <<< "$out" | tail -1)
                            [[ -n "$f" ]] && h="$h · $f" ;;
        "interrogate (docstrings)")
                            h=$(grep -oE 'RESULT: [A-Z]+ \(minimum: [0-9.]+%, actual: [0-9.]+%\)' <<< "$out" | tail -1) ;;
    esac
    # Fallback: last non-empty line, stripped of pytest's ==== banner padding
    # and surrounding whitespace, so the table never shows a row of equals signs.
    [[ -z "$h" ]] && h="$(grep -v '^[[:space:]]*$' <<< "$out" | tail -1 \
                          | sed -E 's/^[=[:space:]]+//; s/[=[:space:]]+$//')"
    [[ -z "$h" ]] && h="_(no output)_"
    # Keep the table narrow and markdown-safe.
    h="${h//|/\\|}"
    [[ ${#h} -gt 72 ]] && h="${h:0:69}…"
    printf '%s' "$h"
}

# clip <output> — cap runaway output, keeping head and tail
clip() {
    local out="$1" n
    n=$(wc -l <<< "$out" | tr -d ' ')
    if (( n <= MAX_LOG_LINES )); then printf '%s' "$out"; return; fi
    local keep_head=$(( MAX_LOG_LINES / 3 )) keep_tail=$(( MAX_LOG_LINES - MAX_LOG_LINES / 3 ))
    printf '%s\n\n        ⋯ %d lines omitted ⋯\n\n%s' \
        "$(head -n "$keep_head" <<< "$out")" \
        "$(( n - keep_head - keep_tail ))" \
        "$(tail -n "$keep_tail" <<< "$out")"
}

# row <icon> <label> <headline> <secs>
row() {
    local t="$4"
    [[ "$t" == "—" ]] || t="${t}s"
    printf '| %s | %s | %s | %s |\n' "$1" "$2" "$3" "$t" >> "$ROWS"
}

# block <open|closed> <icon> <label> <headline> <cmd> <output>
block() {
    local mode="$1" icon="$2" label="$3" head="$4" cmd="$5" out="$6"
    {
        if [[ "$mode" == open ]]; then printf '<details open>\n'; else printf '<details>\n'; fi
        printf '<summary><b>%s %s</b> — <code>%s</code></summary>\n\n' "$icon" "$label" "$head"
        printf '```console\n$ %s\n```\n\n' "$cmd"
        if [[ -n "${out//[[:space:]]/}" ]]; then
            printf '```\n%s\n```\n\n' "$(clip "$out")"
        else
            printf '_No output — clean._\n\n'
        fi
        printf '</details>\n\n'
    } >> "$BLOCKS"
}

# ---------------------------------------------------------------------------
# run_check <label> <cmd> <tool>
#   <tool> empty      → always runs
#   <tool> a name     → skipped with a warning if not on PATH
#   <tool> a path (/) → skipped with a warning if the file does not exist
# ---------------------------------------------------------------------------
run_check() {
    local label="$1" cmd="$2" tool="$3"
    local output rc missing=0 t0 t1 secs head

    echo ""
    echo "→ $label"

    if [[ -n "$tool" ]]; then
        if [[ "$tool" == */* ]]; then [[ -e "$tool" ]] || missing=1
        else command -v "$tool" >/dev/null 2>&1 || missing=1; fi
    fi

    if [[ $missing -eq 1 ]]; then
        echo "  ⚠️  $tool not found (skipped)"
        row "⚠️" "$label" "not found: \`$tool\`" "0"
        block closed "⚠️" "$label" "skipped — $tool not found" "$cmd" ""
        warnings+=("$label")
        return
    fi

    t0=$(date +%s)
    # pipefail is ESSENTIAL. Three checks pipe into `tail`, and without it $?
    # is tail's exit code — always 0. Before this, a red pytest run reported
    # "pass (exit 0)" and the whole sweep exited clean.
    output=$(set -o pipefail; eval "$cmd" 2>&1); rc=$?
    t1=$(date +%s); secs=$(( t1 - t0 ))
    echo "$output"

    head="$(headline "$label" "$output")"
    if [[ $rc -eq 0 ]]; then
        passes=$(( passes + 1 ))
        row "✅" "$label" "$head" "$secs"
        block closed "✅" "$label" "$head" "$cmd" "$output"
    else
        failures+=("$label")
        row "❌" "$label" "**exit $rc** — $head" "$secs"
        # Red checks open by default: a failure should not require a click.
        block open "❌" "$label" "exit $rc" "$cmd" "$output"
    fi
}

# note_skip <label> — deliberately not run this phase. Distinct from a
# warning: nothing is missing, it just isn't this phase's job.
note_skip() {
    skipped_phase+=("$1")
    row "⊘" "$1" "_not run in \`$SWEEP\`_" "—"
}

# ---------------------------------------------------------------------------
# log_only <label> <cmd>
#   Run a command purely for the record. No row, no pass/fail, no effect on the
#   verdict — the output lands in the log and nowhere else.
#
#   The counterpart to run_assert's rule: a check either asserts a value or it
#   is not a check. Anything that only prints belongs here, so the results
#   table can never present a printout as a verdict.
# ---------------------------------------------------------------------------
log_only() {
    local label="$1" cmd="$2" output
    echo ""
    echo "→ $label (log only)"
    output=$(set -o pipefail; eval "$cmd" 2>&1)
    echo "$output"
    block closed "📄" "$label" "context only — asserts nothing" "$cmd" "$output"
}

# note <icon> <label> <headline> <body>  — for non-command checks
note() {
    row "$1" "$2" "$3" "0"
    { printf '<details>\n<summary><b>%s %s</b> — <code>%s</code></summary>\n\n%s\n\n</details>\n\n' \
        "$1" "$2" "$3" "$4"; } >> "$BLOCKS"
}

# ---------------------------------------------------------------------------
# run_assert <label> <cmd> <tool> <predicate> [predicate-args...]
#
#   The asserting counterpart to run_check, and the reason it exists:
#
#   run_check inherits the command's exit code. For a tool that exits non-zero
#   on failure (mypy, ruff, xenon, pytest) that IS the assertion and run_check
#   is correct. For a tool that exits 0 on principle, it silently conflates
#   "ran" with "passed". That one conflation produced four separate
#   green-but-unverified checks:
#
#     - extract_registry.py returns 0 with parse errors AND with cycles
#       (main() ends `return 0`); criterion 4 was never enforced.
#     - `git status --short` exits 0 on a dirty tree; criterion 9 likewise.
#       Proven live: a post-merge sweep reported "✅ All checks passed" with
#       ` M scripts/verify.sh` sitting in the output of that very check.
#     - the coverage table was read by eye — truncated by `tail -40`, then
#       suppressed by `skip-covered`, so absence became the evidence.
#     - evidence presence wrote to warnings[], which the verdict logic counts
#       as a pass; criterion 8 likewise.
#
#   A check either asserts a value or it is not a check. run_assert therefore
#   takes a PREDICATE as well as a command, and a missing or undeclared
#   predicate is a hard failure of the sweep — never a default, never a skip.
#
#   Predicate contract: receives the command's output as $1 plus any extra
#   args, prints human-readable verdict lines ENDING IN ONE SUMMARY LINE, and
#   returns 0 (pass) / non-zero (fail). That last line becomes the row in the
#   results table, so the table says what was verified rather than what ran.
# ---------------------------------------------------------------------------
run_assert() {
    local label="$1" cmd="$2" tool="$3" predicate="$4"; shift 4
    local output rc missing=0 t0 t1 secs head verdict prc

    echo ""
    echo "→ $label"

    if [[ -z "$predicate" ]] || ! declare -F "$predicate" >/dev/null 2>&1; then
        echo "  ❌ predicate '${predicate:-<none>}' is not a declared function"
        failures+=("$label (no predicate)")
        row "❌" "$label" "**no predicate** — \`${predicate:-<none>}\`" "0"
        block open "❌" "$label" "no predicate" "$cmd" \
            "run_assert requires a predicate function; '${predicate:-<none>}' is not declared. A check that cannot state what it asserts is not a check."
        return
    fi

    if [[ -n "$tool" ]]; then
        if [[ "$tool" == */* ]]; then [[ -e "$tool" ]] || missing=1
        else command -v "$tool" >/dev/null 2>&1 || missing=1; fi
    fi
    if [[ $missing -eq 1 ]]; then
        echo "  ⚠️  $tool not found (skipped)"
        row "⚠️" "$label" "not found: \`$tool\`" "0"
        block closed "⚠️" "$label" "skipped — $tool not found" "$cmd" ""
        warnings+=("$label")
        return
    fi

    t0=$(date +%s)
    output=$(set -o pipefail; eval "$cmd" 2>&1); rc=$?
    t1=$(date +%s); secs=$(( t1 - t0 ))
    echo "$output"

    verdict="$("$predicate" "$output" "$@" 2>&1)"; prc=$?
    [[ -n "$verdict" ]] && echo "$verdict"

    # The predicate's summary line is the headline — the table reports the
    # assertion, not the command's last line of chatter.
    head="$(tail -n 1 <<< "$verdict" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    [[ -z "$head" ]] && head="$(headline "$label" "$output")"
    head="${head//|/\\|}"
    [[ ${#head} -gt 72 ]] && head="${head:0:69}…"

    if [[ $rc -eq 0 && $prc -eq 0 ]]; then
        passes=$(( passes + 1 ))
        row "✅" "$label" "$head" "$secs"
        block closed "✅" "$label" "$head" "$cmd" "$output"$'\n'"$verdict"
    else
        failures+=("$label")
        if [[ $rc -ne 0 ]]; then
            row "❌" "$label" "**exit $rc** — $head" "$secs"
        else
            row "❌" "$label" "**assertion failed** — $head" "$secs"
        fi
        block open "❌" "$label" "exit $rc · assertion $prc" "$cmd" "$output"$'\n'"$verdict"
    fi
}

# ---------------------------------------------------------------------------
# _branch_paths <diff-filter> <root-regex>
#   Source-module paths this branch adds (A) or removes (D) relative to its
#   merge-base with the integration branch. Shared derivation so the coverage
#   assertion and the module count can never disagree about what this task did.
#
#   Deletions are counted, not just additions: `--diff-filter=A` alone
#   false-reds the module total the first time a task removes a module.
# ---------------------------------------------------------------------------
COV_ROOTS='^src/subway_ops/'

_branch_paths() {
    local filter="$1" roots="$2" base_ref
    base_ref="$(git merge-base HEAD "$INTEGRATION_BRANCH" 2>/dev/null)"
    [[ -n "$base_ref" ]] || return 1
    git diff --name-only --diff-filter="$filter" "$base_ref"..HEAD -- '*.py' 2>/dev/null \
        | grep -v '^\.claude/' | grep -v '/tests\?/' | grep -v '^tests/' \
        | grep -E "$roots" || true
}

# ---------------------------------------------------------------------------
# PREDICATES — each takes the command output as $1, prints verdict lines, and
# ends with exactly one summary line.
# ---------------------------------------------------------------------------

# assert_pytest_green — the regression suite completed and nothing failed.
assert_pytest_green() {
    local out="$1" summary
    if grep -qE '[0-9]+ (failed|error)' <<< "$out"; then
        echo "pytest: FAILURES — $(grep -oE '[0-9]+ (failed|error)[a-z]*' <<< "$out" | tail -1)"
        return 1
    fi
    summary="$(grep -oE '[0-9]+ passed[^=]*' <<< "$out" | tail -1 | sed -E 's/[[:space:]]+$//')"
    if [[ -z "$summary" ]]; then
        echo "pytest: no 'N passed' summary — the run did not complete"
        return 1
    fi
    echo "pytest: $summary"
    return 0
}

# assert_worktree_clean — criterion 9. `git status --short` exits 0 regardless,
# so the emptiness of its output is the only thing that carries the verdict.
assert_worktree_clean() {
    local out="$1" n
    if [[ -n "${out//[[:space:]]/}" ]]; then
        n="$(grep -c . <<< "$out")"
        echo "worktree: NOT CLEAN — $n path(s) modified or untracked"
        return 1
    fi
    echo "worktree: clean"
    return 0
}

# assert_coverage <out> <coverage.json> — criterion 3. Project TOTAL from the
# table, plus a per-module assertion on everything this task added.
assert_coverage() {
    local out="$1" cov_json="$2" total added rc=0 detail
    total="$(grep -oE 'TOTAL +[0-9]+ +[0-9]+ +[0-9]+%' <<< "$out" | tail -1 | awk '{print $4}')"
    [[ -n "$total" ]] || total="unknown"

    added="$(_branch_paths A "$COV_ROOTS")"
    if [[ -z "${added//[[:space:]]/}" ]]; then
        echo "coverage: total $total · 0 modules added vs '$INTEGRATION_BRANCH' — nothing to assert"
        return 0
    fi
    if [[ ! -f "$cov_json" ]]; then
        echo "coverage: total $total · no JSON report at $cov_json"
        return 1
    fi
    detail="$(python3 - "$cov_json" $added <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
files = report.get("files", {})
paths = sys.argv[2:]
bad = []
for path in paths:
    entry = files.get(path)
    if entry is None:
        print(f"  {path} — NOT MEASURED by this run")
        bad.append(path)
        continue
    summary = entry["summary"]
    pct = summary["percent_covered"]
    if pct < 100.0:
        print(f"  {path} — {pct:.1f}% ({summary['missing_lines']} lines uncovered)")
        bad.append(path)
    else:
        print(f"  {path} — 100% ({summary['num_statements']} statements)")
print(f"__COUNT__ {len(paths) - len(bad)} {len(paths)}")
sys.exit(1 if bad else 0)
PY
)"; rc=$?
    grep -v '^__COUNT__' <<< "$detail"
    echo "coverage: total $total · $(grep '^__COUNT__' <<< "$detail" \
        | awk '{print $2 "/" $3}') added module(s) at 100%"
    return "$rc"
}

# evidence_report — criterion 8. Reports only; the predicate below decides.
# Matched BY CONTENT, not filename: the journal is per-task T-XXXX.md plus a
# shared LEDGER.md, and ledger drafts are date-named.
evidence_report() {
    local journal_file="$JOURNAL_DIR/${TASK_ID}.md" lines decision_line ids id
    if [[ ! -d "$JOURNAL_DIR" ]]; then
        echo "⚠️ journal: directory not found — $JOURNAL_DIR"
        return
    fi
    if [[ ! -f "$journal_file" ]]; then
        echo "⚠️ journal: no ${TASK_ID}.md in $JOURNAL_DIR"
        return
    fi

    lines="$(wc -l < "$journal_file" | tr -d ' ')"
    # A stub is worse than nothing: it satisfies a filename check while
    # recording nothing. 40 is well under the 150 target, far above a
    # placeholder.
    if [[ "$lines" -lt 40 ]]; then
        echo "⚠️ journal: ${TASK_ID}.md is only $lines lines — stub, not an entry"
    else
        echo "✅ journal: ${TASK_ID}.md ($lines lines)"
    fi

    # Verity required a ledger draft per task. Here most tasks decide nothing,
    # so a blanket requirement would train everyone to write a fake one. The
    # requirement is instead that the entry STATES the position explicitly:
    # a `Decisions:` line reading either `none` or a list of D-### ids. Silence
    # is not an answer — an author who decided something and did not say so is
    # exactly the drift this system exists to catch.
    decision_line="$(grep -m1 -E '^Decisions:' "$journal_file" 2>/dev/null)"
    if [[ -z "$decision_line" ]]; then
        echo "⚠️ decisions: ${TASK_ID}.md has no 'Decisions:' line (use 'Decisions: none' if none)"
    elif grep -qiE '^Decisions:[[:space:]]*none[[:space:]]*$' <<< "$decision_line"; then
        echo "✅ decisions: none declared"
    else
        ids="$(grep -oE 'D-[0-9]{3}' <<< "$decision_line" | sort -u)"
        if [[ -z "$ids" ]]; then
            echo "⚠️ decisions: '$decision_line' names no D-### id and is not 'none'"
        else
            while read -r id; do
                [[ -n "$id" ]] || continue
                if grep -q -- "$id" "$DECISIONS_FILE" 2>/dev/null; then
                    echo "✅ decisions: $id present in $(basename "$DECISIONS_FILE")"
                else
                    echo "⚠️ decisions: $id declared in the journal but absent from $(basename "$DECISIONS_FILE")"
                fi
            done <<< "$ids"
        fi
    fi
}

# assert_evidence_complete — every reported item must be present.
assert_evidence_complete() {
    local out="$1" missing
    missing="$(grep -c '^⚠️' <<< "$out")"
    if [[ "$missing" -gt 0 ]]; then
        echo "evidence: INCOMPLETE — $missing item(s) missing"
        return 1
    fi
    echo "evidence: journal present, decisions declared"
    return 0
}

# ===========================================================================
#  CORE CHECKS
# ===========================================================================
run_check "Test discovery"           "$RUN pytest --collect-only -q 2>&1 | tail -5"                           ""
# No pipe. `| tail -20` truncated the failure list to the summary banner — the
# same evidence-loss bug as the coverage table. `-v` is dropped with it: it
# existed to give `tail` something to show, and without the pipe it is 3000
# lines of PASSED. Default pytest prints dots for passes and full tracebacks
# for failures, which is strictly more failure evidence per line. clip() caps
# the log block; the predicate carries the verdict.
run_assert "Full regression"         "$RUN pytest"                               "" assert_pytest_green

if in_phase pre-merge post-merge; then
    run_assert "Coverage" \
        "$RUN pytest --cov=src/subway_ops --cov-report=term-missing:skip-covered --cov-report=json:'$TMP/coverage.json' -q" \
        "" assert_coverage "$TMP/coverage.json"
else
    note_skip "Coverage"
fi

# pyproject already sets strict = true; passing --strict makes the bar explicit
# at the call site rather than leaving it to a config file nobody re-reads.
run_check "mypy --strict"            "$RUN mypy --strict src/"                                                ""
run_check "ruff check"               "$RUN ruff check ."                                                      ""
# `ruff format --check .` is NOT here yet, and its absence is deliberate rather
# than forgotten: this repo has never been formatted, so the check reds on ~58
# pre-existing files. Landing that reformat inside the harness change would bury
# it in a thousand-line diff. Tracked as B-0005; add this line back in the same
# task that runs the formatter.
# isort is intentionally absent: ruff's I rules cover import ordering, and two
# tools with opinions about the same thing is how format wars start.

if in_phase pre-merge post-merge; then
    run_check "uv lock check"            "uv lock --check"                                                        ""
    run_check "bandit (security)"        "$RUN bandit -r src/subway_ops -ll -q"                                   "bandit"
    run_check "vulture (dead code)"      "$RUN vulture src/subway_ops tools --min-confidence 80"                  "vulture"
    run_check "interrogate (docstrings)" "$RUN interrogate src/subway_ops"                                        "interrogate"
    run_check "xenon (complexity)"       "$RUN xenon --max-absolute C --max-modules B --max-average A src/subway_ops" "xenon"
else
    for c in "uv lock check" "bandit (security)" "vulture (dead code)" \
             "interrogate (docstrings)" "xenon (complexity)"; do note_skip "$c"; done
fi

# git status catches exactly the class of thing that hid for three turns:
# an uncommitted modification to this very script riding along through checkouts.
#
# journal/ and test_logs/ are excluded, and NOTHING else is (D-023). The journal
# entry is written moments before this gate runs, by design — Rule 5 orders it
# that way so the evidence check below can assert it exists. Excluding those two
# paths does not weaken what this assertion was written for: the gate script is
# not in either of them.
if in_phase pre-merge post-merge; then
    run_assert "git status" \
        "git status --short -- . ':(exclude)journal' ':(exclude)test_logs'" \
        "" assert_worktree_clean
    # The graph asserts nothing — it is context for whoever reads the log, not
    # a check. It goes to the log only; a results table that lists it is
    # counting a printout as a verdict.
    log_only "git graph"             "git log --oneline --graph --decorate -10"
else
    note_skip "git status"
fi

# ===========================================================================
#  CONTRACT SPINE
# ===========================================================================
# Verity's spine was a Python module registry plus a contract-drift check. This
# system's contract is different in kind: it is a database schema plus a set of
# laws that CLAUDE.md used to state in prose and nothing enforced. So the spine
# here is (1) the invariant checks and (2) schema drift.

# --- Invariants: the rules that used to be prose ---------------------------
# Runs in every phase, including adhoc. These are cheap, they are the rules
# most likely to be broken by an ordinary edit, and the whole reason they exist
# is that a "non-negotiable" nobody checks is a suggestion.
run_check "invariants" "$RUN python -m tools.verify_invariants" "$INVARIANTS_DIR"

# --- Schema drift -----------------------------------------------------------
# The analogue of drift_check.py. A migration that changes a column type, drops
# a NOT NULL, or renames a key is a contract change; it should be visible in the
# gate rather than discovered by a 3am ingest failure.
if in_phase pre-merge post-merge; then
    mkdir -p "$DRIFT_DIR"
    run_check "schema snapshot" \
        "$RUN python '$SCHEMA_SNAPSHOT' --out '$SCHEMA_OUT'" \
        "$SCHEMA_SNAPSHOT"
else
    note_skip "schema snapshot"
fi

if in_phase pre-merge; then
    if [[ ! -f "$BASELINE" ]]; then
        echo ""; echo "→ schema drift"
        echo "  ⚠️  no baseline at $BASELINE"
        echo "     the previous task's post-merge sweep writes it"
        note "❌" "schema drift" "NO BASELINE — gate cannot run" \
            "No baseline at \`$BASELINE\`.\n\nWritten by the previous task's \`post-merge\` sweep. Without it the drift check does not run, and a sweep that skips its own gate must not report green.\n\nFirst run only: seed it with \`uv run python scripts/schema_snapshot.py --out .drift/schema-before.json\` and say so in the journal."
        failures+=("schema drift (no baseline)")
    elif [[ ! -f "$SCHEMA_OUT" ]]; then
        note "❌" "schema drift" "no current snapshot to compare" \
            "The snapshot step did not produce \`$SCHEMA_OUT\`, so there is nothing to diff against the baseline."
        failures+=("schema drift (no snapshot)")
    else
        # D-024: a task that intends to change the schema declares the change
        # in .drift/expected/<T-id>.txt, and the gate checks the observed drift
        # against that statement — undeclared drift fails, and so does a
        # declaration that no longer matches. With no declaration the check
        # behaves exactly as it did before: any drift is a failure.
        DRIFT_DECL="$REPO_ROOT_DIR/.drift/expected/${TASK_ID}.txt"
        if [[ -f "$DRIFT_DECL" ]]; then
            run_check "schema drift" \
                "$RUN python '$SCHEMA_SNAPSHOT' --diff --before '$BASELINE' --after '$SCHEMA_OUT' --expected '$DRIFT_DECL'" \
                "$SCHEMA_SNAPSHOT"
        else
            run_check "schema drift" \
                "$RUN python '$SCHEMA_SNAPSHOT' --diff --before '$BASELINE' --after '$SCHEMA_OUT'" \
                "$SCHEMA_SNAPSHOT"
        fi
    fi
else
    note_skip "schema drift"
fi

# --- Codex consistency ------------------------------------------------------
# The kit erratum: verify.sh SILENTLY SKIPS a missing verify-codex.sh, which is
# a vacuous pass. Closed here — if the codex exists, its gate must exist too.
# Before Part 2 lands there is no codex at all, and that is a visible skip
# rather than a silent one.
if in_phase pre-merge post-merge; then
    if [[ ! -d "$CODEX_ROOT" ]]; then
        note "⊘" "verify-codex.sh" "no codex yet — Part 2 not landed" \
            "\`$CODEX_ROOT\` does not exist. The design authority has not been authored yet (D-017), so there is nothing to check. This becomes a FAILURE the moment \`codex/\` appears without its gate."
        skipped_phase+=("verify-codex.sh (no codex yet)")
    elif [[ ! -x "$CODEX_ROOT/verify-codex.sh" ]]; then
        note "❌" "verify-codex.sh" "codex exists but its gate does not" \
            "\`$CODEX_ROOT\` exists but \`verify-codex.sh\` is missing or not executable. The upstream kit skipped silently here, which let an unchecked codex report green. Ship the gate."
        failures+=("verify-codex.sh (missing gate)")
    else
        run_check "verify-codex.sh" "cd '$CODEX_ROOT' && ./verify-codex.sh" ""
    fi
else
    note_skip "verify-codex.sh"
fi

# ===========================================================================
#  EVIDENCE PRESENCE  (pre-merge only)
# ===========================================================================
# The model writes the journal entry and ledger drafts — it is the only thing
# that knows why it made the choices it made. This never writes them; it only
# checks they exist. Both matched BY CONTENT, not filename: the journal is one
# shared append-only JOURNAL.md, and ledger drafts are date-named.
if in_phase pre-merge; then
    run_assert "Evidence presence" "evidence_report" "" assert_evidence_complete
else
    note_skip "Evidence presence"
fi

# ===========================================================================
#  BASELINE ROTATION  (post-merge only)
# ===========================================================================
if in_phase post-merge; then
    echo ""; echo "→ Baseline rotation"
    if [[ ${#failures[@]} -ne 0 ]]; then
        echo "  ⚠️  not rotating — this sweep has ${#failures[@]} failure(s)"
        note "⚠️" "Baseline rotation" "skipped — sweep is red" \
            "Not rotating. A red sweep must not enshrine a broken schema as the baseline every future drift check is measured against."
        warnings+=("Baseline rotation (sweep red)")
    elif [[ "$BRANCH" != "$INTEGRATION_BRANCH" ]]; then
        echo "  ⚠️  not rotating — on '$BRANCH', not the integration branch '$INTEGRATION_BRANCH'"
        note "⚠️" "Baseline rotation" "skipped — not on \`$INTEGRATION_BRANCH\`" \
            "Rotation writes the baseline every future drift check is measured against. Running \`post-merge\` from a task branch would enshrine a mid-build schema, and the corruption would not surface until the NEXT task's drift check reported nonsense."
        warnings+=("Baseline rotation (not on integration branch)")
    elif ! git rev-parse -q --verify "HEAD^2" >/dev/null 2>&1; then
        echo "  ⚠️  not rotating — HEAD ($COMMIT) is not a merge commit"
        note "⚠️" "Baseline rotation" "skipped — HEAD is not a merge" \
            "\`post-merge\` means *after the merge*. HEAD has a single parent, so the merge has not happened yet and this schema is not the post-merge state."
        warnings+=("Baseline rotation (HEAD not a merge)")
    elif [[ ! -f "$SCHEMA_OUT" ]]; then
        echo "  ⚠️  no $SCHEMA_OUT to rotate"
        note "⚠️" "Baseline rotation" "no schema snapshot" "Nothing at \`$SCHEMA_OUT\` to rotate."
        warnings+=("Baseline rotation (no snapshot)")
    else
        mkdir -p "$DRIFT_DIR"
        [[ -f "$BASELINE" ]] && cp "$BASELINE" "$BASELINE.$(date '+%Y%m%dT%H%M%S').bak"
        cp "$SCHEMA_OUT" "$BASELINE"
        echo "  ✅ baseline rotated → $BASELINE"
        echo "     ${TASK_ID}'s schema is now the --before for the next task"
        note "✅" "Baseline rotation" "rotated" \
            "\`$SCHEMA_OUT\` → \`$BASELINE\`\n\nThis is the \`--before\` for the next task's pre-merge drift check."
    fi
else
    note_skip "Baseline rotation"
fi

# ===========================================================================
#  ASSEMBLE THE LOG
# ===========================================================================
RUN_SECS=$(( $(date +%s) - RUN_START ))

if [[ ${#failures[@]} -eq 0 && ${#warnings[@]} -eq 0 ]]; then
    VERDICT="✅ PASSED"; VERDICT_LINE="All checks passed."
elif [[ ${#failures[@]} -eq 0 ]]; then
    VERDICT="✅ PASSED"; VERDICT_LINE="Passed with ${#warnings[@]} warning(s)."
else
    VERDICT="❌ FAILED"; VERDICT_LINE="${#failures[@]} check(s) failed."
fi

if [[ ! -f "$LOG_FILE" ]]; then
    cat > "$LOG_FILE" <<EOF
# $TASK_ID · \`$SWEEP\`

Append-only record of **$SWEEP** sweeps for $TASK_ID.
One file per phase; see the sibling files in this directory for the others.

| | |
|---|---|
| **Task** | $TASK_ID |
| **Phase** | \`$SWEEP\` |
| **Repo** | $REPO |
| **Created** | $TIMESTAMP |

EOF
fi

RUN_N=$(( $(grep -c '^## Run ' "$LOG_FILE" 2>/dev/null) + 1 ))

{
    printf '\n<br>\n\n---\n\n'
    printf '## Run %d · %s · %s\n\n' "$RUN_N" "$VERDICT" "$TIMESTAMP"
    printf '> **%s**  %d passed · %d failed · %d warned · %d n/a · %ss total\n\n' \
        "$VERDICT_LINE" "$passes" "${#failures[@]}" "${#warnings[@]}" "${#skipped_phase[@]}" "$RUN_SECS"
    printf '| | |\n|---|---|\n'
    printf '| Branch | `%s` |\n' "$BRANCH"
    printf '| Commit | `%s` |\n' "$COMMIT"
    printf '| Gate | `verify.sh @ %s` (`%s`)%s |\n' "$SCRIPT_BLOB" "$SCRIPT_COMMIT" "$SCRIPT_DIRTY"
    printf '| Worktree | `%s` |\n' "$WORKTREE"
    printf '| Integration branch | `%s` |\n' "$INTEGRATION_BRANCH"
    if [[ ${#failures[@]} -gt 0 ]]; then printf '| **Failed** | %s |\n' "${failures[*]}"; fi
    if [[ ${#warnings[@]} -gt 0 ]]; then printf '| Warned | %s |\n' "${warnings[*]}"; fi
    printf '\n### Results\n\n'
    printf '| | Check | Detail | Time |\n|---|---|---|---|\n'
    cat "$ROWS"
    printf '\n### Output\n\n'
    cat "$BLOCKS"
} >> "$LOG_FILE"

# ===========================================================================
#  CONSOLE SUMMARY
# ===========================================================================
echo ""
echo "──────────────────────────────────────────"
if [[ ${#failures[@]} -eq 0 && ${#warnings[@]} -eq 0 ]]; then
    echo "✅ All checks passed."
elif [[ ${#failures[@]} -eq 0 ]]; then
    echo "✅ Passed."
    echo "⚠️  Skipped (${#warnings[@]}): ${warnings[*]}"
else
    echo "❌ Failed (${#failures[@]}): ${failures[*]}"
    [[ ${#warnings[@]} -gt 0 ]] && echo "⚠️  Skipped (${#warnings[@]}): ${warnings[*]}"
fi
[[ ${#skipped_phase[@]} -gt 0 ]] && echo "⊘  Not in this phase (${#skipped_phase[@]}): ${skipped_phase[*]}"
echo "Sweep:  $SWEEP  (run #$RUN_N in this file)"
echo "Branch: $BRANCH @ $COMMIT"
echo "Gate:   verify.sh @ $SCRIPT_BLOB ($SCRIPT_COMMIT)$SCRIPT_DIRTY"
echo "Log:    $LOG_FILE"
echo "──────────────────────────────────────────"

[[ ${#failures[@]} -eq 0 ]] && exit 0 || exit 1
