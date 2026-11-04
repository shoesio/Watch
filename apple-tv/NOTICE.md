# Source and licence notices

The Watch 1.4 source bundle is provided under GNU GPL version 3 or later; see LICENSE.txt.

The native Channel 5, ITV and U account/wire/FairPlay modules (`Channel5*.swift`, `ITVAccount.swift`, `ITVLive.swift`, `ITVPlayback.swift`, `UAccount.swift`, `UService.swift` and `UPlayback.swift`) adapt code from usefulappmaker's Telly, itself derived from Beeb, under GPL-3.0-or-later:
https://github.com/usefulappmaker/Telly-public
Reviewed revision: e7622f30f3e8e14afb4e32c98689f246d6221bb3.
Changes: separate Watch Keychain namespaces, Watch error wording, selective extraction of ITV wire/AVFoundation code, playback configuration adapters, QR account views and integration with Watch’s existing player, Pi metadata and shared progress. ITV catalogue metadata parsing adapts the public schema documented by the same source.

Provider protected media is handled by Apple's AVContentKeySession and the provider's licence service. No decrypted media or content keys are exported to the Pi. Provider login sessions, signing material and expiring playback URLs are not included in this source bundle.

Broadcaster names, logos, programme artwork and content belong to their respective owners. Watch is independent and is not endorsed by those services. TMDB data is used with the acknowledgement displayed in Settings.


The native Channel 4 live adapter (`Channel4Playback.swift`) adapts Telly's GPL-3.0-or-later source, file revision `935318a1391622ceb6b1b74da724660cbe1d17f4`, reviewed 4 November 2026:
https://github.com/usefulappmaker/Telly-public/blob/935318a1391622ceb6b1b74da724660cbe1d17f4/Telly/Channel4Playback.swift
Changes: Watch error types, shared PlaybackSource/NativeKeySession adapters, static phase diagnostics, live-only capability negotiation and integration with existing programme metadata. Subtitle-master rewriting and on-demand routing are not enabled by this change. The public client metadata envelope identifies the licence-service address; media decryption remains entirely inside Apple's FairPlay session. Content keys, provider credentials and playback URLs are not logged or exported.


BBC UHD additions (build 28) adapt Telly/Beeb's UHD identity storage, DASH parser, local HLS server and CMAF fragment normalization under GPL-3.0-or-later from https://github.com/usefulappmaker/Telly-public . The user's existing TwinVine setup is provisioned privately through the developer device connection and retained in device-only Keychain storage. No certificate, private key, account password or signed media URL is bundled in the app or repository. BBC server trust validation remains enabled. Protected DASH presentations are rejected; no media decryption is added.
