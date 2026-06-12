#!/usr/bin/env bash
set -euo pipefail

packages=(
  packages/astx
  packages/irx
  packages/arx
  packages/pyarx
)

for package_dir in "${packages[@]}"; do
  (
    cd "${package_dir}"
    poetry publish
  )
done
