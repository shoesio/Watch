# Pi-to-Samsung Watch launcher

The small Samsung accepts authenticated legacy remote commands on port 55000. A manual Smart Hub → Down → Enter test successfully opened Watch, confirmed on the physical TV.

`remote.py` sends only navigation keys. It keeps the paired identity `Pi Watch remote`, and does not expose power-off or service-menu commands.

`launch.py` can run one calibrated launch or monitor a power cycle. It deliberately does nothing when started while the television is already on. Automatic mode requires at least 20 seconds of failed connectivity, then 25 seconds of stable remote availability, and issues just one launch attempt per cycle. Short network interruptions do not trigger it. A failed launch is logged, without retrying menu commands.

`settings.json` starts with `calibrated: false`. Verify the Smart Hub highlighted position after a real power cycle before changing it. The navigation path may change if the TV remembers the last selection or if tiles move. This is remote navigation, not a direct app-ID launch API.

Run checks: `python -m unittest test_launch` from this directory.

The system service is separate from the existing playback and app gateway services. Stop/disable it with `sudo systemctl disable --now samsung-watch-launcher.service` if startup navigation is unwanted.
