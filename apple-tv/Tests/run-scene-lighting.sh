#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
watch_scene_test_dir=$(mktemp -d)
trap 'rm -rf "$watch_scene_test_dir"' EXIT
xcrun swiftc -parse-as-library Watch/SceneColour.swift Watch/HueCalibration.swift Tests/SceneLighting/Main.swift -o "$watch_scene_test_dir/checks"
"$watch_scene_test_dir/checks"
