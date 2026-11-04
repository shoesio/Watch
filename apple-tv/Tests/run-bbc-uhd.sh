#!/bin/zsh
set -eu
cd "$(dirname "$0")/.."
watch_uhd_test_dir=$(mktemp -d)
trap 'rm -rf "$watch_uhd_test_dir"' EXIT
xcrun swiftc -parse-as-library Watch/BBCUHDMetadata.swift Watch/BBCDASHManifest.swift Watch/BBCLocalHLSServer.swift Watch/BBCFMP4Normalizer.swift Tests/BBCUHDTests.swift -o "$watch_uhd_test_dir/uhd-tests"
"$watch_uhd_test_dir/uhd-tests"
