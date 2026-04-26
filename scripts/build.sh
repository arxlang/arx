#!/usr/bin/env bash
set -euo pipefail

packages=(
  packages/astx
  packages/irx
  packages/arx
)

for package_dir in "${packages[@]}"; do
  rm -rf "${package_dir}/dist"
  (
    cd "${package_dir}"
    poetry build
  )
done
