# Source and licence notices

The Watch 1.4 source bundle is provided under GNU GPL version 3 or later; see LICENSE.txt.

The native Channel 5, ITV and U account/wire/FairPlay modules (`Channel5*.swift`, `ITVAccount.swift`, `ITVLive.swift`, `ITVPlayback.swift`, `UAccount.swift`, `UService.swift` and `UPlayback.swift`) adapt code from usefulappmaker's Telly, itself derived from Beeb, under GPL-3.0-or-later:
https://github.com/usefulappmaker/Telly-public
Reviewed revision: e7622f30f3e8e14afb4e32c98689f246d6221bb3.
Changes: separate Watch Keychain namespaces, Watch error wording, selective extraction of ITV wire/AVFoundation code, playback configuration adapters, QR account views and integration with Watch’s existing player, Pi metadata and shared progress. ITV catalogue metadata parsing adapts the public schema documented by the same source.

Provider protected media is handled by Apple's AVContentKeySession and the provider's licence service. No decrypted media or content keys are exported to the Pi. Provider login sessions, signing material and expiring playback URLs are not included in this source bundle.

Broadcaster names, logos, programme artwork and content belong to their respective owners. Watch is independent and is not endorsed by those services. TMDB data is used with the acknowledgement displayed in Settings.
