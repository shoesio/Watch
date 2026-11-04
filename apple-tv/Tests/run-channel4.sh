#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
check_dir=$(mktemp -d)
trap 'rm -rf "$check_dir"' EXIT
xcrun swiftc -parse-as-library Watch/Channel5Service.swift Watch/Channel5Account.swift Watch/Channel5Playback.swift Watch/Channel4Playback.swift Watch/UService.swift Watch/UAccount.swift Watch/UPlayback.swift Watch/ITVAccount.swift Watch/ITVLive.swift Watch/ITVPlayback.swift Watch/Models.swift Tests/Channel4/Main.swift -o "$check_dir/checks"
"$check_dir/checks" "$@"
