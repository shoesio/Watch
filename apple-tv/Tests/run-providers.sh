#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
check_dir=$(mktemp -d)
trap 'rm -rf "$check_dir"' EXIT
xcrun swiftc Watch/ITVAccount.swift Watch/ITVLive.swift Watch/UService.swift Watch/UAccount.swift Tests/Providers/Shims.swift Tests/Providers/Main.swift -o "$check_dir/checks"
"$check_dir/checks"
