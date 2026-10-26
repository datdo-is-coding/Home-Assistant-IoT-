# KWS calibration extension — 26/10/2026

**Stopped at user request:** “tiếp tục, ko train nữa”. Do not resume training or
request further training recordings without a new explicit instruction. Candidates
remain private experimental artifacts; keep original model active.

User explicitly approved calibration/retraining after confirming the captured DDF8
utterance is clear and complete. This extends the original spec's no-training limit;
all transport, relay, enrollment and ownership constraints remain unchanged.

## Design

Keep TinyKWS's ten labels and SubBox inference, with the current MFCC dimensions,
normalization and bounded audio task. Prefer fine-tuning the existing checkpoint
with original examples plus microphone-domain data over replacing architecture.
Keep the active header/binary until a separate candidate passes validation. Use
raw microphone recordings only in the private backup directory; no cloud upload.

Split new recordings by complete session, never random overlapping windows. Keep
validation/test sessions out of training and parameter selection. Existing
X_test/y_test remains a regression holdout. Quantize/fold weights into the existing
C++ inference layout and compare its output with the trained reference before
considering hardware deployment. The old ONNX byte-array exporter does not produce
the actual scalar C++ weight header and cannot be treated as a drop-in exporter.

Acceptance: report held-out per-class accuracy, exact complete-command matches,
wrong action/room counts and noise/unknown false commands. Reject any observed
wrong command in the pilot holdout; report limited sample coverage honestly.
Recheck inference <250ms and transport/session regressions on real hardware.
Do not tune thresholds solely to the one failing phrase. Retain empty bindings
until voice acceptance passes and the user supplies explicit channel roles.

## Steps

- [x] Reproduce on PCM, compare host/ESP probabilities and check feature extraction.
- [ ] Confirm current checkpoint → scalar-header equivalence and establish baseline.
- [ ] Collect labelled mic training sessions and independent held-out sessions.
- [ ] Train candidate using existing TinyKWS with reproducible split/seed/metrics.
- [ ] Export weight-only INT8 candidate with FP32/C++ parity and regression checks.
- [ ] Test fresh real utterances/noise; deploy only candidate that passes gates.
- [ ] Record limitations and complete original integration checks when possible.

## Progress

- Baseline355: PyTorch79.44%, C++INT8 79.15%, label agreement99.72%; scalar export
  matches within max probability error0.02767. Current live phrase fails both.
- Dedicated training environment installed outside repo. Candidate tooling uses
  original train/val/test, whole-session mic split, separate output directory,
  firmware MFCC and per-channel INT8/BN-fold export. Three tests pass.
- Seven captured sessions have uncertain labels; no training run started using
  them. App did not render native audio. A loopback-only annotation page is
  available at127.0.0.1:8767; browser automation is disabled by user settings.
  Individual re-recording request for “bật” is also pending. No model promoted.

### Candidate results (not deployment acceptance)

Human annotation resolved seven training labels; added bếp. Candidate-v1 and-v2b
are stored privately. V2b gets5/6 complete single-word validation replays correct,
old355 accuracy78.59%, but still omits đèn from the diagnostic full sentence.
125ms host spike recovers that sentence but violates current hardware timing
budget; unchanged250ms firmware cadence retained. INT8 export max probability
error0.04466 exceeds0.04 gate. Neither candidate deployed. Four requested fresh
sessions (bật,tắt,silence,unknown) remain pending. Firmware+training suite30/30 pass.

## Final recording check before stopping

Four requested sessions were received completely. Candidate-v2b recognizes bật/tắt
and returns empty on silence, but maps “hôm nay trời đẹp” to “phòng ngủ” (125ms
spike: “đèn phòng ngủ”). Negative acceptance fails; no candidate promoted. The
subsequent five training-negative requests are cancelled by the user’s stop-training
instruction. No training process or capture server is running at cleanup.
