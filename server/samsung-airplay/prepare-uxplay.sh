#!/bin/sh
# Recreate the tested UxPlay source and callback adapter without modifying services.
set -eu
asset_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
checkout=${1:-./uxplay-src}
if [ -e "$checkout" ]; then
    echo "Destination already exists: $checkout" >&2
    exit 1
fi
git init "$checkout"
git -C "$checkout" remote add origin https://github.com/FDH2/UxPlay.git
git -C "$checkout" fetch --depth 1 origin 234b407e2e7a8a9a33adf293f0e56fd539658b1e
git -C "$checkout" checkout --detach FETCH_HEAD
git -C "$checkout" apply "$asset_dir/uxplay.patch"
cp "$asset_dir/samsung_bridge.h" "$checkout/samsung_bridge.h"
cmake -S "$checkout" -B "$checkout/build" -DNO_X11_DEPS=ON
cmake --build "$checkout/build" -j3
