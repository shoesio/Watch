# Watch

Watch brings a shared television library to Apple TV, Home Assistant and Samsung Smart Hub, backed by a Raspberry Pi.

| Part | Source | Purpose |
| --- | --- | --- |
| Pi server / host | [server](server/) | Installed bridge, shared catalogue and playback services, companion gateways and service units |
| Apple TV app | [apple-tv](apple-tv/) | Native tvOS app and Xcode project |
| Home Assistant dashboard | [home-assistant](home-assistant/) | Watch card, dashboard YAML, browser player and bridge source |
| Samsung app | [samsung](samsung/) | Samsung Orsay widget, packaging tools and launcher |

This repository groups the existing components without changing the running installation. The server folder preserves the installed directory names and imports. Component READMEs describe their existing configuration and operation; paths and network addresses in examples reflect the original Pi installation and should be adapted for another host.

## Getting started

1. Read [the Pi host guide](server/README.md) and configure the three services using their `settings.example.json` files.
2. Open `apple-tv/Watch.xcodeproj` in Xcode for the tvOS app. `apple-tv/Gateway` links to the server's Watch gateway.
3. Add the Home Assistant card resource and use `home-assistant/dashboard.yaml`.
4. Build the Samsung widget with `samsung/build.py`; provide its device key privately at packaging time.

## Source snapshot

Imported on 29 October 2026. Server runtime files were read from the Pi, with local source bundles supplying project assets, documentation and tests. The Samsung widget was also read from the Pi. The Apple TV Xcode project and Home Assistant source came from the existing development workspace. The dashboard YAML matches the installed Watch dashboard.

Development continues in the original workspace, so subsequent edits there are not automatically committed here. This is a source snapshot, not an automated deployment or synchronisation system.

## Private configuration

Real `settings.json` files, provider sessions, Home Assistant tokens, pairing/device keys, signing files, catalogues, viewing history, cache, diagnostics and built app packages are excluded. Samsung's checked-in connection file contains only a placeholder. Recreate private configuration locally from the examples; do not commit credentials.

## Licences and acknowledgements

Apple TV includes GPL-3.0-or-later code and its notices in [apple-tv/NOTICE.md](apple-tv/NOTICE.md) and [apple-tv/LICENSE.txt](apple-tv/LICENSE.txt). HLS.js notices and broadcaster artwork attribution remain alongside the components. See component notices for third-party terms; no blanket licence is assigned to unrelated components.
