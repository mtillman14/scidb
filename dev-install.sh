#!/bin/bash
# Install all packages in editable mode (dependency order)
set -e

# Resolve the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing all SciStack packages in editable mode..."

# Layer 0: no internal deps
python -m pip install -e "$SCRIPT_DIR/scicanonicalhash"
python -m pip install -e "$SCRIPT_DIR/path-gen"
python -m pip install -e "$SCRIPT_DIR/scifor"
python -m pip install -e "$SCRIPT_DIR/sciduckdb"

# Layer 1: depends on scicanonicalhash
python -m pip install -e "$SCRIPT_DIR/scilineage"

# Layer 2: depends on thunk, scipathgen, scicanonicalhash, sciduckdb, scirun
python -m pip install -e "$SCRIPT_DIR/scidb"

# Layer 3: depends on scidb
python -m pip install -e "$SCRIPT_DIR/scimatlab"
python -m pip install -e "$SCRIPT_DIR/scihist"
python -m pip install -e "$SCRIPT_DIR/scidb-net"

echo "All packages installed in editable mode."
