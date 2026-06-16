#!/usr/bin/env bash
# Run pytest for every package that has tests.
# Execute from the repo root: bash run_tests.sh
# Optional flags are forwarded to pytest, e.g.: bash run_tests.sh -x -q

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRA_ARGS=("$@")

PACKAGES=(
    scicanonicalhash
    path-gen
    scifor
    sciduckdb
    scilineage
    scidb
    scihist
    scidb-net
)

# scimatlab requires a MATLAB licence; skip unless MATLAB is available.
if command -v matlab &>/dev/null; then
    PACKAGES+=(scimatlab)
fi

PASS=()
FAIL=()

for pkg in "${PACKAGES[@]}"; do
    pkg_dir="$REPO_ROOT/$pkg"
    test_dir="$pkg_dir/tests"

    if [[ ! -d "$test_dir" ]]; then
        echo "⚠  Skipping $pkg — no tests/ directory found"
        continue
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $pkg"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if pytest "$test_dir" "${EXTRA_ARGS[@]}"; then
        PASS+=("$pkg")
    else
        FAIL+=("$pkg")
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PASSED (${#PASS[@]}): ${PASS[*]:-—}"
echo "  FAILED (${#FAIL[@]}): ${FAIL[*]:-—}"

[[ ${#FAIL[@]} -eq 0 ]]
