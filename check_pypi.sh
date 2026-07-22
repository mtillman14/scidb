#!/usr/bin/env bash
# Checks which monorepo packages are live on PyPI.
# A 200 means the package exists on PyPI; 404 means it is NOT uploaded yet.

packages=(
  scistacklog
  scifor
  scistack-gui
  sciduckdb
  scilineage
  scistack-db
  scicanonicalhash
  scimatlab
  scistack
  scipathgen
  scidb-net
  scihist
)

echo "Checking PyPI..."
for p in "${packages[@]}"; do
  code=$(curl -s -m 15 -o /dev/null -w "%{http_code}" "https://pypi.org/pypi/$p/json")
  if [ "$code" = "200" ]; then
    echo "  ON PyPI    : $p"
  elif [ "$code" = "404" ]; then
    echo "  NOT on PyPI: $p"
  else
    echo "  ??? ($code) : $p"
  fi
done
