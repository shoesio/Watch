# Autostart an Orsay app with Samsung's Auto Ticker profiles

**Confirmed on Samsung LT27B551 / T27B551, main firmware T-MX10PMDEUC 1013.0, Smart Hub runtime T-INFOLINK2012-1026.** Watch opened automatically after a normal remote off/on cycle. This is a result on this specific TV, not a compatibility claim for every Orsay or Tizen model.

The successful method was to register the ordinary developer app as the ticker startup target through the native **TVMW** plugin. The grey **Auto Ticker — Off** menu did not prevent it. No root, Skype hook, native boot script, Pi remote-button sequence or additional firmware update was used for this registration.

## The two settings that made it work

| TVMW profile | Meaning | Original reading on this TV | Successful reading |
| --- | --- | --- | --- |
| `0` | Ticker application ID | `"0"` | `"SamsungWatch"` |
| `3` | Ticker autoboot | `"0"` | `"1"` |
| `4` | Ticker duration | `"0"` | Unchanged |
| `7` | Ticker safe flag | `"0"` | Unchanged |

The native API calls were:

```javascript
// These are the operations performed by the explicitly triggered trial.
// Do not put them in normal application startup code.
tvmw.SetProfile(0, 'SamsungWatch');
tvmw.GetProfile(0); // must read back 'SamsungWatch'
tvmw.SetProfile(3, '1');
tvmw.GetProfile(3); // must read back '1'
```

`tvmw` is an object created after the page is ready:

```javascript
var tvmw = document.createElement('object');
tvmw.id = 'watchStartupTVMW';
tvmw.setAttribute('classid', 'clsid:SAMSUNG-INFOLINK-TVMW');
tvmw.style.cssText = 'position:absolute;width:0px;height:0px';
document.body.appendChild(tvmw);
```

The target must be the **actual installed widget ID**, observed here as `window.curWidget.id === 'SamsungWatch'`. It is not the visible title, ZIP filename, version, or a guessed numeric store ID. The installed path on this TV was `/mtd_down/widgets/user/SamsungWatch/index.html`.

**Keep the app manifest as an ordinary app:**

```xml
<ticker itemtype="boolean">n</ticker>
```

Setting `<ticker>y</ticker>` was the failed route: installation was rejected with **“Ticker Apps is detected”**. The working route kept `ticker=n` and changed only profiles 0 and 3.

## Reproduce the tested procedure

The supplied [read-only probe](autoboot/probe.js), [explicit-action trial](autoboot/trial.js), and [package staging helper](autoboot/stage.py) preserve the working app and let the owner enable or undo registration deliberately. The trial is deliberately restricted to the tested model code `12_X10PLUS_MFM`, widget ID `SamsungWatch`, and original `0/0` settings. It refuses unexpected settings or another app's registration. It does not enable autostart merely because the app is opened.

1. **Install and manually open the normal app first.** Confirm that it works, identify its actual widget ID, and retain its working package. Leave the usual Pi key-sequence launcher disabled for the native startup test.
2. **Read and record the existing profiles.** Stage the probe, synchronise user applications, open Watch and wait for its report. Record the values *and* whether each getter returned normally. An access exception, empty string and string `"0"` are different results; do not treat an access failure as an off setting. The probe also records the model/runtime and widget identity, without reading account credentials.
3. **Stage the explicit trial.** On this installation, the report goes to the Pi's existing port-80 `/event` collector; the gateway service does not need restarting. Preserve the original report privately before changing settings.
4. **Press RED in the trial app to enable.** The trial first calls `SetProfile(3, '0')` with the existing value and requires an accepted return plus matching readback. It then sets the ID and enable flag in the order shown above, checking readback after each. On this TV, setters returned `1` and the getters returned the requested strings. A failed step attempts to restore the recorded `0/0` baseline and separately reports a failed restoration.
5. **Test an actual power cycle.** Leave **TV** as the source, switch off with the remote for about 20 seconds, switch on and leave the remote alone. Watch opened automatically; a subsequent probe still reported `SamsungWatch` / `1`. Getter success alone is not a substitute for this test.
6. **Publish a clean, higher-version app.** Remove the trial/probe scripts, retain the same installed widget identity and synchronise again. Registration is stored by the TV; the normal app does not need to reapply it on every launch. The clean app must not contain the RED/GREEN trial panel or automatic profile writes.

The staging helper is run **on the Pi**. It takes the package currently offered by `widgetlist.xml` as its base, backs it and the install list up privately, preserves the paired connection and other assets, and refuses an existing output filename or an intervening installer change.

For example, when the current app is 0.329 and these example version numbers are unused:

```sh
cd /home/jhewes/samsung-watch/autoboot

# Read-only report. Copy/save the report before the next step.
/home/jhewes/tv-favourites-venv/bin/python stage.py --version 0.330

# Explicit RED/GREEN controls; opening the app does not change profiles.
/home/jhewes/tv-favourites-venv/bin/python stage.py --version 0.331 --trial

# After the power-cycle test, remove both diagnostic scripts.
/home/jhewes/tv-favourites-venv/bin/python stage.py --version 0.332 --remove-probe
```

These are **separate stages**, with a TV synchronisation and observation between each command. Choose fresh, increasing versions for the actual installer state. Do not run all three at once, publish an older version, or re-run this procedure just to install an ordinary Watch update. The example paths and LAN event-collector address in the scripts belong to this installation and need adapting for another host. The collector is supplied by the existing install server; the staging helper does not create it.

## Undo registration

If the clean app is already installed, first stage the explicit trial again with a fresh higher version and `--trial`, then synchronise and open it. Opening it still makes no profile writes.

For this TV's recorded original `0/0` baseline, **GREEN** in the trial restores settings in this order:

```javascript
tvmw.SetProfile(3, '0'); // disable autoboot first; require GetProfile(3) === '0'
tvmw.SetProfile(0, '0'); // restore the original target; require GetProfile(0) === '0'
```

The restoration refuses an unrelated startup app selection. If restoration fails, keep the TV on and inspect the readbacks rather than assuming it was undone. A different TV may have different original values: the supplied hardcoded `0/0` restoration is not a generic factory reset. Reinstalling a clean package removes diagnostics but **does not disable the persistent startup registration**. Restoring a package and restoring TV profiles are separate actions.

## Limits and practical observations

- **Source matters:** startup worked from TV mode; an EXT test did not launch Watch. HDMI startup was not verified because no HDMI device was connected. Do not promise startup from every input.
- **Smart Hub still takes time:** the owner observed about 16 seconds before Smart Hub began starting. The app cannot run code during that earlier tuner-only period.
- **Empty tuner warnings and snow are separate:** without channels/aerial, the TV displayed an autotune dialog and later analogue snow. Watch could still start. Native registration does not supply a channel list or suppress an earlier TV modal.
- **Keep the widget ID on updates:** changing `SamsungWatch`, uninstalling/reinstalling, factory resets, mains disconnection and other firmware versions were not covered by the confirmed power-cycle test. The main firmware 1013.0 is distinct from NNAVI's `T-INFOLINK2012-1026` runtime string.
- **Region is not established as the deciding factor:** the Smart Hub region had already been changed to US during earlier investigation. The successful profile method was not separately retested in UK mode. The region change alone did not make ticker-tagged developer packages install.
- **API permissions vary:** Samsung's SDK marks these methods as System operations. They happened to be callable in this developer app on this set. Getter/setter availability and actual launch behaviour need checking on another model; this is not a Tizen API recipe.
- **Screen presentation is separate:** `presentation.js` is an unpublished, fixture-tested prototype, not part of the confirmed autostart solution. It is not needed for the two-profile registration. A pale playback picture was ultimately traced by the owner to an LCD display setting, not the app's HTML overlay.

## Evidence, references and checks

The [chronological findings](../research/samsung-autoboot/FINDINGS.md) record the rejected ticker package, exact getter results, accepted setters and successful power-cycle result. Early hypotheses there are followed by the confirmed outcome above. Private reports, paired app packages and recovery backups are intentionally not committed.

Samsung's [DeviceAPI Guide 2.20](https://freethetv2011.s3.amazonaws.com/DeviceAPI_Guide%5BV2.20%5D%5B1%5D.pdf) documents TVMW `GetProfile` / `SetProfile` and profile IDs 0, 3, 4 and 7; see printed pages 232, 237–238 and 258–259. The [application development guide](https://freethetv2011.s3.amazonaws.com/App_Development_Guide_for_Samsung_Smart_TV%5BV1.20%5D%5B1%5D.pdf) describes the ticker manifest property. These are Samsung-authored legacy documents hosted on a third-party archive. The hardware test, rather than the documentation alone, establishes this model's result.

Run the local checks without contacting or changing a TV:

```sh
node samsung/autoboot/test-probe.cjs
node samsung/autoboot/test-trial.cjs
python3 -m unittest discover -s samsung/autoboot -p test_stage.py
```

They cover read-only probing, deliberate enable/restore actions, rejected writes and rollback, unrelated selections, and package/connection preservation. They do not replace a physical startup test on another TV.
