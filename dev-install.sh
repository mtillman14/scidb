#!/bin/bash
# Install all packages in editable mode (dependency order)
set -e

# Resolve the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing all SciStack packages in editable mode..."

# Layer 0: no internal deps
pip install -e $SCRIPT_DIR/canonical-hash
pip install -e $SCRIPT_DIR/path-gen
pip install -e $SCRIPT_DIR/scifor
pip install -e $SCRIPT_DIR/sciduck

# Layer 1: depends on canonicalhash
pip install -e $SCRIPT_DIR/scilineage

# Layer 2: depends on thunk, scipathgen, canonicalhash, sciduckdb, scirun
pip install -e $SCRIPT_DIR/scidb

# Layer 3: depends on scidb
pip install -e $SCRIPT_DIR/sci-matlab
pip install -e $SCRIPT_DIR/scihist-lib
pip install -e $SCRIPT_DIR/scidb-net

echo "All packages installed in editable mode."
