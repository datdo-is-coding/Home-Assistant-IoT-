# HomeCompetition — energy tab and scrolling performance

User request: direct energy visualization in bottom navigation; reduce home-tab
scroll/touch jank on connected Android. Keep live Firebase source and explicit
missing/stale readings. No changes to cloud rules, hardware or relay protocol.

Implementation:
- Add /energy as a stateful shell branch (five destinations on phone/tablet).
  Preserve home scroll/filter state when switching tabs. Existing report shortcuts
  switch to that branch. Add actual per-channel power bars and accumulated kWh;
  never manufacture hourly history from a current cumulative reading.
- Reduce rebuilds from unchanged Firebase status/scope/counts, keep name/favorite
  scope isolation and live channel updates. Lazily build room/controller lists.
- Regression tests for navigation/state, data/error/empty states, repeated
  telemetry notification costs and freshness. Measure synthetic120-channel
  scrolling/update load in profile mode on connected phone; label it synthetic.
- Install optimized build in place, preserving Firebase login. Debug builds are
  not a valid release-speed benchmark.

## Results

- Added a fifth stateful destination, Điện năng, between Thiết bị and Kịch bản;
  phone navigation bar and tablet rail both expose it. Existing shortcuts go to
  the same branch. Home filter and scroll position survive tab changes.
- Energy tab shows actual measured total W, summed known per-channel cumulative
  kWh with coverage, and relative power bars by channel. Offline/unknown power
  is excluded; unknown values are not zeros. No fabricated time history.
- Removed whole-client watch at app root; session identity still rebuilds on
  account change. Shell watches only connection/error fields. Home-name storage
  reloads only on URL/user change; late results from other scopes are rejected.
- Home watches total count rather than the complete reading list; the status
  strip owns its own subscription. Room/controller rows now use lazy SliverList.
- Regression:10 unchanged client notifications previously caused10 root rebuilds;
  now0, and no repeated home-name preference reads. Channel reading subscriptions
  remain live. Navigation/large-text/zero/empty/offline energy cases covered.

Physical Android profile-mode measurement, same phone and same fixture:
120 synthetic channels, nominal5Hz updates, warm-up then8 bidirectional flings.

| Metric | Before | After |
| --- | --- | --- |
| Recorded frames |571|575|
| UI build median |17.913ms|5.113ms|
| UI build p95 |26.216ms|14.749ms|
| UI build p99 |32.922ms|34.044ms|
| UI builds over16.667ms |359/571 (62.9%)|19/575 (3.3%)|
| Raster p95 |2.640ms|4.094ms|
| Raster frames over16.667ms |0|0|
| Update ticks observed |115|84|

UI build p95 improved43.7%; long-tail p99 did not improve. These are timings of
individual build/raster stages, not an end-to-end FPS guarantee. The same scroll
steps took less wall time after optimization, so fewer timer ticks occurred.
Both captures used AOT profile mode and no physical relay operations. Initial
watchPerformance attempt failed its VM loopback GC query; only successful direct
FrameTiming captures above are used. JSON summaries are saved under evidence/.

Verification: flutter analyze clean;154 tests passed. Android release APK build
and on-device installation verification follow below. The existing release
configuration falls back to the debug signing key, preserving the fingerprint
already used for Google login; this is not production release signing.

## Installed build and acceptance

Release build1.2.0/code15 passed. Regenerating plugin metadata with a normal
`flutter build apk --release` resolved a stale integration_test registrant left
from profile testing; no generated file was hand-edited. Signing SHA1 matches
69:52:90:33:FA:F8:FF:A5:9B:BD:BE:53:37:EF:85:11:6A:14:9A:E5.
Installed named APK HomeCompetition-1.2.0.apk and launched MainActivity. Startup
log showed no Overlay/unhandled/framework/fatal error markers.

Important test side effect: this Flutter Driver version uninstalls the test app
on successful teardown unless `--keep-app-running` is used. Android's new first
install timestamp exposed this. Local authentication/preferences may have been
reset; cloud data was untouched. User was informed, signed in again and explicitly
confirmed "Đã thử — mượt hơn, thấy tab Điện năng" on the release build. Future
runs on a user's installed app must keep it running or use a separate test ID;
never rely on the CLI help describing teardown only as stopping the app.

Reproduce (on an authorized test device, preserving the install after testing):

```sh
HOME_COMPETITION_PERF_OUTPUT=/tmp/homecompetition-performance.json flutter drive \
  --profile --keep-app-running --driver=test_driver/performance_driver.dart \
  --target=integration_test/home_scroll_performance_test.dart -d <device-id>
```

Install the main release entrypoint again after a test run. No electrical load
verification or persisted time-series history was added in this change.
