#!/bin/bash
# Install all packages in editable mode (dependency order)
set -e

# Resolve the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing all SciStack packages in editable mode..."

# Layer 0: no internal deps
pip install -e $SCRIPT_DIR/scistacklog
pip install -e $SCRIPT_DIR/scicanonicalhash
pip install -e $SCRIPT_DIR/path-gen
pip install -e $SCRIPT_DIR/scifor
pip install -e $SCRIPT_DIR/sciduckdb

# Layer 1: depends on scicanonicalhash
pip install -e $SCRIPT_DIR/scilineage

# Layer 2: depends on thunk, scipathgen, scicanonicalhash, sciduckdb, scirun
pip install -e $SCRIPT_DIR/scidb

# Layer 3: depends on scidb
pip install -e $SCRIPT_DIR/scimatlab
pip install -e $SCRIPT_DIR/scihist
pip install -e $SCRIPT_DIR/scidb-net

echo "All packages installed in editable mode."
