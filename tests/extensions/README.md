# Hive extension Behave collection

Canonical tests for the four extension repositories in [gnome-extensions-hive](https://github.com/gnome-extensions-hive). `collection.json` records repository/packaging coordinates, UUIDs and schemas. Supported Shell versions remain in each installed candidate's `metadata.json`.

## Coverage

| Tag | Extension | Functional scenarios |
|---|---|---|
| `just_perfection` | Just Perfection | Panel desktop/overview behavior, search, dash/launcher rendering, disable restoration |
| `sjc_gold` | SJC Gold Widget | Rendered header/buy/sell labels, independent position changes, card removal and single-card reenable |
| `shade_inactive_windows` | Shade Inactive Windows Reborn | Two real windows, focus-driven brightness, app exclusion, effect/transition removal |
| `stock_market` | Stock Market Widget | Explicit watchlist rows, English/Vietnamese labels, position changes, card removal and single-card reenable |

Common tagged examples exercise enable/disable/reenable and accessible preferences for each profile. The functional oracles inspect public Shell actor/effect rendering and real GSettings changes, not extension-private controller data. Shading is a brightness effect, not reduced window opacity.

## Execution contract

Run **only in a disposable guest** with the exact candidate package installed and discoverable before GNOME Shell starts. The suite does not download extensions, start VMs, force metadata compatibility, or install dependencies on the developer's host.

Prerequisites: real Wayland GNOME session; working session bus and user journal; trusted Shell.Eval test probe; `gnome-extensions` and `gsettings`; compiled package schemas; dogtail/AT-SPI for preferences; Text Editor and Calculator for shading. Use qecore-headless to establish the guest session environment, as the existing GNOME suites do. Gold quote retrieval additionally requires Python and curl_cffi; Stock Market requires Python and `/usr/bin/curl`.

Guest command (example for Just Perfection):

```bash
qecore-headless "behave tests/extensions/features --tags @just_perfection -D disposable_guest=true --format json.pretty --outfile results.json"
```

No guest opt-in means failed setup before desktop actions. Missing packages, failed Shell probes, unavailable journal cursors and failed settings restoration are errors, not successful skips. Settings and original enabled state are restored; functional steps clean up test-owned windows/overview state. The hooks check GNOME Shell JS/GObject warnings/errors in the scenario's user-journal interval. This does not claim exhaustive warning or leak detection.

The active-fade teardown case temporarily forces guest Shell animations and restores the original flag. It requires a 1x, 1000ms transition and checks removal immediately. The timing guard uses the transition's observed elapsed time plus wall-clock time since that successful probe, which must remain below its duration minus a 100ms safety margin. Earlier polling does not consume the budget; an expired fade cannot satisfy cleanup through natural completion.

Journal classification uses both the message and journald's `GLIB_DOMAIN`/`PRIORITY` fields. Gjs/GLib-GObject warning/critical records and recognizable JavaScript exceptions fail; ordinary provider HTTP/timeout console errors are allowed in the non-price UI lane. Test-owned window/overview cleanup runs before settings restoration and the journal check. The existing shared quarantine gate is honored, but a quarantined mandatory scenario still cannot satisfy the eventual service gate.

Development checks do not require a guest:

```bash
behave --dry-run tests/extensions/features
python3 -m pytest tests/unit/test_extension_session.py -q
```

A dry run proves step resolution, **not extension compatibility**. The GNOME OS gate must reject empty/all-skipped/undefined/untested mandatory scenarios, irrespective of the more permissive summary behavior of existing suites.

## Deferred GNOME OS runtime work

- [#908](https://github.com/projectbluefin/testsuite/issues/908): prove genuine GNOME OS provisioning and desktop/AT-SPI/input prerequisites.
- [#909](https://github.com/projectbluefin/testsuite/issues/909): stage exact artifacts before session startup, supply deterministic HTTPS fixtures and execute this collection on GNOME OS.

GNOME OS validation remains mandatory but is **not established by this test-content change**. Bluefin image smoke cannot substitute. Successful price formatting, partial-data/cache/outage recovery and delayed-fetch cancellation need the real provider fixture lane from #909. These tests do not replace helper subprocess output with fabricated quote JSON and do not use live provider quotes as a CI oracle. The Stock Market empty-watchlist language/position cases use the extension's existing no-fetch path; the selected-symbol case still runs its real bounded helper/fallback.

## Sources

Developer rationale first: [Jonas Ådahl, Automated testing of GNOME Shell (2022-12-02)](https://blogs.gnome.org/shell-dev/2022/12/02/automated-testing-of-gnome-shell/) explains full-session, virtual-input and warning-free testing.

Pinned behavior sources:
- [Just Perfection](https://github.com/gnome-extensions-hive/just-perfection/tree/6e82a6ebf8e9578f2ffe4e06b88f5d23f600b947): schema and `src/lib/Manager.js`/`API.js`.
- [SJC Gold](https://github.com/gnome-extensions-hive/sjc-gold-binhnguyensoft.com/tree/1588c7683d113e42d2f36a69165a9bacd6b1d95b): extension, helper and schema.
- [Shade](https://github.com/gnome-extensions-hive/Shade-Inactive-Windows-Reborn/tree/59b0afaf7320f72ef408621dafac19ec0214705b): brightness effect, focus handling and schema.
- [Stock Market](https://github.com/gnome-extensions-hive/stock-market-binhnguyensoft.com/tree/667e40171ca6249b846e72cf28e314c5f3a79832): extension, language strings, helper and schema.

[GNOME's OCI contribution guide](https://gnome.pages.gitlab.gnome.org/gnome-build-meta/docs/contributing-oci.html) documents bootc-compatible GNOME OS images for testing/development; [published outputs](https://gnome.pages.gitlab.gnome.org/gnome-build-meta/docs/ci-outputs.html) names actual tags. Their existence is not proof that our current provisioner boots them correctly. The supported distribution channel remains DDI/sysupdate.
