#!/usr/bin/env bash

pushd packages/astx || exit
poetry publish
popd || return

pushd packages/irx || exit
poetry publish
popd || return

pushd packages/arx || exit
poetry publish
popd || return
