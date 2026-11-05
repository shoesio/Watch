# Raspberry Pi host

The three source trees preserve the current installation layout:

| Directory | Service | Port | Role |
| --- | --- | --- | --- |
| `tv-favourites` | `tv-favourites.service` | 8109 | Provider access, catalogue sync, Home Assistant bridge and browser playback |
| `watch-appletv` | `watch-appletv.service` | 8115 | Shared discovery, recommendations, pairing and Apple TV playback gateway |
| `samsung-watch` | `samsung-watch.service` | 8113 | Samsung gateway, widget hosting and packaging |

The original host uses `/home/jhewes/` and a shared `tv-favourites-venv`. Service files and example settings retain those paths. Copy each tree to the corresponding installation directory, create the Python environment from the supplied requirements, and adapt service paths and example settings for your own host. Keep private data in a separate directory and copy example settings to ignored `settings.json` files. See the [Home Assistant guide](../home-assistant/README.md), [Apple TV guide](../apple-tv/README.md) and [Samsung guide](../samsung/README.md) for provider setup and pairing.

The HA and Samsung folders also retain their self-contained development bundles, including backend modules. For the captured live deployment, use these server trees as the reference runtime sources. Copies have not been refactored into a shared package because that would change existing deployment and import behaviour.

No running services were restarted or changed during import. Provider credentials, device keys, personal catalogues and caches are intentionally absent.

## Checks for this import

All imported Python files passed syntax parsing, and both dashboard/widget JavaScript entry points passed Node syntax checks. The paging/recommendation tests can be run from the repository root with:

```sh
PYTHONPATH=server/tv-favourites python3 -m unittest discover -s server/watch-appletv -p test_suggestion_paging.py
```

Install the component requirements before running the remaining backend suites. Some historical browser tests expect the original private `dashboard-fixture.json`; that personal catalogue fixture is intentionally excluded from this repository. No fresh Xcode build or physical playback test was performed for this source import.


## Optional Watch scene lighting

The Apple TV gateway accepts `scene_light_entity` in its private settings file (default `null`). Set it to a colour-capable Home Assistant `light.*` entity, then enable Scene lighting in Watch Settings. The installed example target is `light.living_room_behind_tv`. The existing bridge Home Assistant credential stays server-side. Paired `/scene-light` updates require ownership of an active playback ticket and accept hue plus a neutral/white flag; callers cannot select arbitrary entities or brightness. Session cleanup and abandoned-lease expiry restore the captured lamp state; manual overrides take priority. See [Apple TV notes](../apple-tv/README.md) for sampling availability and validation limits.
