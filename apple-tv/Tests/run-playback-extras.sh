#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
check_dir=$(mktemp -d)
trap 'rm -rf "$check_dir"' EXIT
xcrun swiftc -parse-as-library Watch/Models.swift Watch/PlaybackExtras.swift Tests/PlaybackExtras/Main.swift -o "$check_dir/checks"
"$check_dir/checks"
