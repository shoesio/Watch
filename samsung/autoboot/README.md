# Native Samsung Watch autostart

**Confirmed working on the T27B551 with T-MX10PMDEUC 1013.0.** The owner verified Watch launched automatically after a normal remote off/on cycle, with persistent TVMW readings `SamsungWatch` / `1`. The Pi's remote-button launcher remained disabled. The current normal Watch release is **0.329**; it retains the same app identity and does not write startup profiles.

See **[the complete Auto Ticker setup and recovery guide](../AUTOSTART.md)** for the exact API calls, ordinary `ticker=n` manifest, model/runtime, readback checks, staged RED/GREEN trial, power-cycle test, package cleanup and limitations.

| File | Purpose | Status |
| --- | --- | --- |
| `probe.js` | Read only TVMW profiles 0/3/4/7 plus model/runtime/widget identity | Tested on the TV |
| `trial.js` | Explicit RED enables; GREEN restores the recorded original settings | Enable/readback/power cycle confirmed on the TV; restoration path fixture-tested |
| `stage.py` | Add/remove diagnostics using the current Pi install package, with private backup and asset checks | Package-tested and used for 0.323–0.325 |
| `presentation.js` | Attempt full-screen presentation/banner handling | Unpublished prototype; fixture-tested only; not required for autostart |
| `test-*.cjs`, `test_stage.py` | Local checks; no real TV profile writes | Run before changing the helpers |

The trial refuses another model code, widget identity, an unexpected baseline, or an unrelated startup selection. It never enables anything on page load. Do not remove those guards to treat one TV's result as universal support.

The probe and trial send selected diagnostics to the existing LAN install server's `/event` collector. Adapt the host address and private backup paths for another installation; do not publish household reports or paired app packages.

[Chronological research and test evidence](../../research/samsung-autoboot/FINDINGS.md) is retained separately. SDK manuals and raw device reports are not included in Git.
