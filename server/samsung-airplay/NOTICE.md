# Source and licence notes

UxPlay is developed at https://github.com/FDH2/UxPlay and is GPLv3 software. The tested base revision is `234b407e2e7a8a9a33adf293f0e56fd539658b1e` (experimental 1.74). Its licence text is retained in `LICENSE.UxPlay`; the upstream copyright notices remain in the source recreated by `prepare-uxplay.sh`.

`uxplay.patch` and `samsung_bridge.h` adapt UxPlay's HLS callbacks. Treat the modified UxPlay program, including this callback glue, under UxPlay's GPLv3 terms. The Python adapter, configuration, diagnostics and documentation are recorded alongside the existing Watch components; no new blanket licence is assigned to unrelated Watch code.

No broadcaster media, signed stream URLs, account sessions, receiver keys or proprietary Samsung firmware are included. Network addresses and account paths in the service examples describe the original private installation and need adaptation for another host.
