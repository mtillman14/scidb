#!/bin/bash
# Install all packages in editable mode (dependency order)
set -e

# Resolve the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing all SciStack packages in editable mode..."

# Layer 0: no internal deps
pip install -e $SCRIPT_DIR/scistacklog --no-deps
pip install -e $SCRIPT_DIR/scicanonicalhash --no-deps
pip install -e $SCRIPT_DIR/path-gen --no-deps
pip install -e $SCRIPT_DIR/scifor --no-deps
pip install -e $SCRIPT_DIR/sciduckdb --no-deps

# Layer 1: depends on scicanonicalhash
pip install -e $SCRIPT_DIR/scilineage --no-deps

# Layer 2: depends on scipathgen, scicanonicalhash, sciduck-db
pip install -e $SCRIPT_DIR/scidb --no-deps

# Layer 3: depends on scidb
pip install -e $SCRIPT_DIR/scimatlab --no-deps
pip install -e $SCRIPT_DIR/scihist --no-deps
pip install -e $SCRIPT_DIR/scidb-net --no-deps
pip install -e $SCRIPT_DIR/scistack --no-deps
pip install -e $SCRIPT_DIR/scistack-gui --no-deps

echo "All packages installed in editable mode."
