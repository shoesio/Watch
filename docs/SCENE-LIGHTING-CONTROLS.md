# Playback scene-lighting controls

Apple TV playback controls include a **Scene lighting** menu. Changes apply immediately and persist on this Apple TV. They do not alter the saved hue calibration.

- **Sample window:** Off, 2, 5, 10 or 20 seconds. Chooses the predominant neighbouring hue cluster across recent samples, rather than mixing unrelated colours. Longer windows resist brief scene cuts.
- **Fade time:** 0.5–8 seconds. Lamp transition duration. The existing three-second fade remains the default.
- **Look ahead:** Off or 0.5–3 seconds. Optional muted companion decoder reads the same current source, without preparing a new gateway session. Lead ramps from zero over eight seconds after play/resume/seek. The menu reports availability. Default is Off.
- **Sampling interval:** 0.5–4 seconds between frame samples; default two seconds.
- **Neutral scenes → white:** When disabled, neutral frames hold the preceding colour.
- **Match scene saturation:** Follow the picture’s colour strength. Off uses the fixed saturation control (default 100%).
- **Match scene brightness:** Follow the sampled picture brightness. Near-black scenes turn the lamp off; subsequent brighter scenes turn it back on. Off preserves the starting brightness. Switching matching off restores the starting brightness. Both matching options default off.

Look-ahead yields when the main programme has less than six seconds buffered, rejects mismatched alternative durations and companion video above 1080p, and falls back to the visible picture when future frames are unavailable. A same-version BBC HD source may be used alongside UHD playback. Protected streams that do not expose frames remain unsupported. Additional decoding/network load and real-world lamp alignment require physical-device verification.

The paired, session-owned `/scene-light` endpoint accepts optional `saturation` (0–100, default 100) `transition` (0–10 seconds, default 3), and `brightness` (0–100%; zero turns off; -1/default preserves the starting brightness). Existing callers retain their previous behaviour. Calibration keeps its separate short transition. Original lamp state restoration and manual override detection remain active.
