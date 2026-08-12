#!/usr/bin/env bash
# verify-codex.sh — deterministic consistency gate for the Subway Ops codex.
#
# Ported from the Burst cleanup kit's v1 edition. Same contract: exit 0 all
# clear, 1 on any failure, and A MISSING CHECKER IS A FAILURE, NEVER A SKIP —
# a check that cannot run must not report green.
#
# Run from the codex root, or set CODEX_ROOT. scripts/verify.sh invokes it at
# pre-merge and post-merge.
CODEX_ROOT="${CODEX_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
TOOLS_DIR="${CODEX_ROOT}/tools/verify_codex"

if [ -t 1 ]; then G='\033[0;32m'; R='\033[0;31m'; N='\033[0m'; else G=''; R=''; N=''; fi
PASS=0; FAIL=0

run_py() {  # run_py "<label>" <script>
    local label="$1" script="$2" out rc
    if [ ! -f "${TOOLS_DIR}/${script}" ]; then
        FAIL=$((FAIL + 1))
        printf "${R}[FAIL]${N} %s — checker missing: %s\n" "$label" "$script"
        return
    fi
    out=$(python3 "${TOOLS_DIR}/${script}" "${CODEX_ROOT}" 2>&1); rc=$?
    if [ $rc -eq 0 ]; then
        PASS=$((PASS + 1)); printf "${G}[PASS]${N} %s\n" "$label"
    else
        FAIL=$((FAIL + 1)); printf "${R}[FAIL]${N} %s\n" "$label"
        printf "%s\n" "$out" | sed 's/^/       /' | head -12
    fi
}

printf "Subway Ops Codex Consistency Suite (4 checks)\n"
printf "============================================\n"
run_py "Internal link integrity"                       check_links.py
run_py "Chapter index matches the tree"                check_chapter_index.py
run_py "Chapter numbering: no duplicate prefixes"      check_prefixes.py
run_py "No placeholders in an authoritative chapter"   check_no_placeholders.py

printf "═══════════════════════════\n  ${G}Passed:${N} %d   ${R}Failed:${N} %d\n" "$PASS" "$FAIL"
if [ "$FAIL" -eq 0 ]; then
    printf "${G}✓ All codex consistency checks passed.${N}\n"; exit 0
fi
printf "${R}✗ %d check(s) failed.${N}\n" "$FAIL"; exit 1
