RESULT: TV downloaded 0.102 but rejected installation with “Ticker Apps is detected”, reported by user. No UK-specific cause established. Installer now offers non-ticker recovery 0.103, preserving all original 0.101 app code; the higher version avoids a downgrade. Automatic remote launcher remains disabled.

# Native startup trial 0.102

Staged as the sole installation-list entry, retaining the SamsungWatch identity. The archive is copied from the physically proven 0.101 Pi package. Only `<ver>` (0.102) and `<ticker>` (y) change; app code, pairing key, icons, fullwidget and source-control flags are identical. This isolates whether ticker eligibility works now that single-app installation works.

1. In Smart Hub, synchronise user applications from server 192.168.0.146.
2. Confirm SamsungWatch installs and opens manually.
3. Look in Smart Hub settings → Service Manager → Auto Ticker for SamsungWatch.
4. Only if offered, select it, switch off/on and confirm automatic opening.

Installation, ticker eligibility and native power-on opening are separate, pending physical tests. The Pi key-sequence launcher is disabled.

The working archive and prior installer list are preserved in `/home/jhewes/tv-favourites-private/backups/watch-ticker-0102`. To restore the server to the known working release:

```sh
/home/jhewes/tv-favourites-venv/bin/python /home/jhewes/samsung-watch/stage-ticker.py --restore
```

Then synchronise user apps on the TV to reinstall 0.101. If the TV refuses a lower version, a recovery package with a higher version and ticker disabled will be needed. No working source files or playback services were changed by staging this trial.
