# Samsung Watch autoboot investigation

These are chronological investigation notes. For the current, reproducible instructions and confirmed limitations, use the [Auto Ticker guide](../../samsung/AUTOSTART.md). Early uncertainties below are superseded by the later hardware results. The current app release is 0.328; historical references to 0.323–0.326 describe the investigation packages. Raw reports and downloaded manuals are not committed.

29 October 2026. Target: Samsung T27B551, T-MX10PMDEUC **1013.0**, confirmed by the owner. 1008.0 in the supplied historical notes is superseded. The owner has downloaded 1015.0 but has not installed it.

**Confirmed outcome:** the owner reports Watch opened automatically after a normal remote off/on cycle. A new TV report at 20:06:39 UTC read ticker ID `SamsungWatch` and autoboot `1`, confirming persistence across that cycle. The Pi key-sequence launcher remained disabled. Native autostart works on this T27B551 with T-MX10PMDEUC 1013.0 and its T-INFOLINK2012-1026 runtime; no root or firmware update was required. Watch 0.325, with the diagnostic/banner removed and the same app identity, is now ready to synchronise. That clean-package update has been verified structurally but not yet physically re-tested on the TV. No root package, firmware image, boot script or remote-navigation automation has been installed or enabled.

## Evidence from this actual TV

The read-only 0.323 probe returned from `192.168.0.123`:

| Reading | Actual result |
| --- | --- |
| NNAVI GetModelCode | `12_X10PLUS_MFM` |
| NNAVI GetFirmware | `T-INFOLINK2012-1026` |
| Runtime widget ID | `SamsungWatch` |
| Runtime widget path | `/mtd_down/widgets/user/SamsungWatch/index.html` |
| TVMW GetProfile(0), ticker ID | string `0` |
| TVMW GetProfile(3), autoboot | string `0` |
| TVMW GetProfile(4), duration | string `0` |
| TVMW GetProfile(7), safe | string `0` |

NNAVI's firmware result identifies the **Smart Hub/runtime**, not the main TV firmware. It does not contradict the owner's 1013.0 report. The path is stronger evidence for this set than assuming the `/mtd_rwcommon` paths used in many ES-series tutorials.

The API returned ordinary strings rather than throwing an access exception. This establishes callable getters, not setters, flash persistence or effective boot support. All-zero values may still reflect limited/stub implementations; the trial tests that distinction.

Existing local trial notes record rejection of a widget with `<ticker>y</ticker>` with the TV message “Ticker Apps is detected”, and a grey Auto Ticker menu. A US region change did not establish a working installation path. The Pi navigation service is still disabled; the owner already observed its unattended launch failure.

A limited TCP check found ports 80, 443, 55000 and 7676 listening; ports 22 and 23 were not reachable during that check. No remote buttons were sent. Two guessed UPnP description paths returned HTTP 401 and were not treated as authenticated access.

## Documented SDK mechanism, not model-specific proof

Samsung's [DeviceAPI Guide 2.20](https://freethetv2011.s3.amazonaws.com/DeviceAPI_Guide%5BV2.20%5D%5B1%5D.pdf), printed pages 232, 237–238 and 258–259, documents:

```javascript
TVMWPlugin.GetProfile(profileID);
TVMWPlugin.SetProfile(profileID, stringValue);
```

It assigns IDs 0/3/4/7 to ticker ID/autoboot/duration/safe respectively, and describes profile storage as persistent. Both getter and setter are marked **System** security operations. The example stores an app ID as a string; that is not proof that a nonnumeric developer ID is accepted by this firmware. The experiment verifies readback and restores the original settings if the ID or flag is rejected.

Samsung's [application development guide](https://freethetv2011.s3.amazonaws.com/App_Development_Guide_for_Samsung_Smart_TV%5BV1.20%5D%5B1%5D.pdf) includes a `ticker` manifest property. Our earlier failed test already exercised that route. Repeating the same manifest change without new evidence is not the next experiment.

Samsung's [exact-model UK support page](https://www.samsung.com/uk/support/model/LT27B551EW/EN/) lists the T-MX10PMDEUC 1015.0 USB update and model manuals. It supplies no evidence that upgrading adds custom-app autostart. The downloaded package directory lists encrypted/signed `.sec` firmware images. Only the archive listing/metadata was inspected; no image has been flashed or patched.

## What SamyGO actually establishes

A [D-series developer thread](https://forum.samygo.tv/viewtopic.php?t=2701) reports selecting the SamyGO widget in Service Manager's ticker autorun menu. Its stated target is D-series ARM sets, not this monitor.

An [E-series experiment](https://forum.samygo.tv/viewtopic.php?p=44129) gives a ticker/Skype arrangement for T-MST10PDEUC, including a stated <=1030.0 starting point. A [later report](https://forum.samygo.tv/viewtopic.php?p=48037) describes ticker startup without working FTP/telnet. That distinction matters: launching a widget, gaining root and starting background services are separate outcomes.

The E-series example modifies `/mtd_rwcommon/widgets/user/SamyGO/config.xml` and references `/mtd_rwcommon/moip/engines/Skype/AutoStart`. Those are historical paths on other sets, **not paths verified on ours**. The exact TV's installed widget path is shown above. No exact installed-widget database filename or schema has been established; inventing a `WidgetManager.db` edit would be unjustified.

The [ES-series rooting guide](https://wiki.samygo.tv/index.php?title=Rooting_the_ES-series) concerns a USB/manual activation route and excludes T-ECPDEUC. Neither its inclusion nor that exclusion proves support for T-MX10PMDEUC. No model/version-specific root procedure, exploit, persistent native hook or recovery method was found for T27B551/T-MX10PMDEUC 1013.0 in the sources checked. This is an evidence gap, not proof that root is impossible.

## Concrete next experiment

Watch 0.324 contains the existing app plus the read-only probe and a visible remote-button trial panel. Opening it makes **no startup writes**.

- RED checks the expected TV model, app identity and backed-up `0/0` baseline. It tries a same-value setter first, then requests ticker ID `SamsungWatch`, reads it back, requests autoboot `1`, and reads that back. Only fields 0 and 3 are changed.
- If a step fails, it attempts to restore autoboot `0` first and ticker ID `0` second. A failure to restore is reported separately.
- GREEN requests that same restoration. It refuses to overwrite an unrelated ticker app selection.
- No other profile fields, region settings, manager files, database, executable or firmware partitions are written.

The `1` enable value and eligibility of an ordinary non-ticker widget are hypotheses to test, not confirmed behaviour on this firmware. Even successful setter return values/readback are insufficient: a normal off/on cycle must launch Watch, and another getter read must establish persistence.

Original readings are backed up on the Pi under:
`/home/jhewes/tv-favourites-private/backups/autoboot-readonly-20261029-200031/tv-startup-before.json`

The previous package/list before 0.324 are under:
`/home/jhewes/tv-favourites-private/backups/autoboot-readonly-20261029-200345`

See [experiment code and app rollback instructions](../../samsung/autoboot/README.md). Restoration of these two settings and removal of the probe are available without a firmware downgrade.

## Escalation only if the profile experiment fails

1. Establish whether the setter is denied, the developer ID is rejected, values fail to persist, or boot ignores otherwise persistent values. These failures require different approaches.
2. Inspect this firmware's widget manager and eligibility checks offline if exact binaries/source can be obtained. Back up actual manager/profile files before any registration edit; do not assume an ES-series database schema.
3. Assess a temporary root route only against this exact model, firmware family and 1013.0 build. Demonstrate an exit/recovery path before persistence. A working app package backup is not a flash/EEPROM backup.
4. Consider a native launch helper only once the real launcher interface, startup lifecycle and recovery access are known. There is no justified command here to replace `exeDSP`, install a blind boot hook, flash another family's firmware or alter EEPROM offsets.

Firmware/root recovery is currently **not established for this exact board**. ExLink availability, electrical pinout, input filtering, backup access and any dual-bank arrangement must be verified on this hardware; examples for other TVs are not a recovery guarantee.

## Live result: profile writes accepted

After the owner pressed RED in 0.324, the TV reported:

| Operation | Return | Readback |
| --- | --- | --- |
| SetProfile(3, '0') — same-value permission check | `1` | `0` |
| SetProfile(0, 'SamsungWatch') | `1` | `SamsungWatch` |
| SetProfile(3, '1') | `1` | `1` |

This verifies setter access and acceptance of the nonnumeric developer app ID on this TV's runtime. It supersedes the earlier uncertainty about those two points. Effective autoboot, survival through a power cycle, and any ticker eligibility check during boot still require the owner's power-cycle test. The Pi navigation launcher remained disabled.

## Confirmed power-cycle result

The owner reported: “It started up into Watch automagically!” The new native report following the cycle retained ticker ID `SamsungWatch` and autoboot `1`. This establishes the requested normal power-on behaviour on this exact set. It does not establish behaviour after mains disconnection, a factory reset, changing app identity, installing other firmware, or every subsequent application update.

The normal app keeps `<ticker>n</ticker>`; the successful route bypasses the unavailable menu by writing its two native profile settings rather than trying to install a ticker-tagged developer package. Duration/safe flags were left at their original `0`. No third-party app or root/Skype hook is involved.

Clean 0.325 retains every underlying playback/style/connection asset from the current app, removing only the two investigation scripts/script references and incrementing its version. It does not run any setters. The previous trial app/list are backed up at `/home/jhewes/tv-favourites-private/backups/autoboot-readonly-20261029-200747-388977`.

## Empty tuner warning after startup

The owner subsequently reported a modal dialog: no channels found, asking whether to start autotune (Yes/No), with no aerial attached. This is not established to be a normal volume/channel banner. No channels have been scanned or fabricated, and no tuner/firmware settings have been changed to suppress it. The next physical test is normal power-on from HDMI to establish whether native Watch autostart works without entering the empty TV tuner.

A full-screen/volume-banner presentation helper exists as an **unpublished prototype** under `samsung/autoboot/presentation.js`. It does not change sources or persistent profiles. Its native calls are fixture-tested, not TV-verified, and it has not been put in the Pi installation package. Banner suppression alone is not assumed to dismiss the autotune modal. The installer remains on clean 0.325 while the HDMI test is pending.

## Later corrections and channel transfer check

The owner clarified that Watch had also booted successfully with the autotune dialog present: the modal and analogue snow are cosmetic startup annoyances, not established blockers. The owner measured about 16 seconds before Smart Hub starts. Watch cannot execute an app-level fix during the earlier tuner-only stage.

EXT power-on did not trigger Watch; HDMI could not be selected without a connected device, so HDMI startup remains untested. Do not generalise this to all external inputs.

The exact-model Samsung manual was retrieved from its official support download and checked: printed page 52 specifies `Menu > Channel > Transfer Channel List` and USB import/export. Read-only SSDP/service-descriptor inspection on this actual TV found MainTVAgent2 at port 7676. Its channel actions expose retrieval/switching/renaming/deletion but no import/upload action. `StartCloneView` is an advertised viewing action, not proof of channel-map cloning/import. The raw service report is retained privately and excluded from Git; no channel mutations were issued. A privileged or undocumented import route is not ruled out, but none is verified. The supported next step is a USB export of this set's own map before attempting model-compatible edits.

The unverified 0.326 screen-presentation package was taken off the installation list when the earlier timing became clear. The installer remains on clean 0.325. Native startup registration was left untouched.

## Playback picture correction

The owner subsequently identified the pale video as an LCD display setting on the TV. Hiding all app graphics did not change it. Release 0.327 removes the temporary black panels and Info-button diagnostic, restores the soft playback gradient and corrects padding/centring; native startup registration is unchanged.
