#!/usr/bin/env bash

pushd packages/astx || exit
cp ../../README.md .
poetry build
popd || return

pushd packages/irx || exit
cp ../../README.md .
poetry build
popd || return

pushd packages/arx || exit
cp ../../README.md .
poetry build
popd || return
