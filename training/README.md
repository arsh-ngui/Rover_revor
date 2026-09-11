# Thermal Motionless-Person Monitor

Detects humans in thermal imagery, tracks each person across frames, and
issues a warning when a tracked person has remained essentially motionless
for a configurable amount of time. Built for search-and-rescue monitoring
in cave/mine environments (Jharkhand). **No posture classification** — see
"Why no posture classes" below.

Warnings are phrased as requiring human verification (*"possible motionless
person — check required"*), never as a claim about someone's medical state.

## Why no posture classes

An earlier version of this project included a standing/sitting/lying
classifier. It was removed: no public thermal dataset has posture labels,
posture information isn't actually needed to answer "has this person
stopped moving", and — critically — the real target sensor (MLX90640,
32×24 pixels) doesn't have enough spatial resolution to distinguish
postures reliably at typical distances anyway (see "MLX90640 feasibility"
below). Dropping posture classification removes the biggest data-scarcity
problem in the project and focuses the whole system on the one signal that
actually matters for this use case: movement over time.

## Detector tiers

The whole pipeline (tracker, movement estimator, motionless timer, warning
engine) talks to detectors through one shared interface
(`src/detection/base.py`), so either backend below drops in without
touching anything downstream:

| Tier | Detector | When to use | Trained? |
|---|---|---|---|
| **1** | `ClassicalBlobPersonDetector` (`src/detection/classical_blob_detector.py`) | **Default / MLX90640-native.** Threshold + connected components. Works directly on a 32×24 array. | No — deterministic algorithm |
| **2** | `YoloPersonDetector` (`src/detection/yolo_detector.py`) | Higher-resolution thermal camera (Lepton 160×120, Boson 320×256, or better) | Yes — see Stage 1 below |

**Why Tier 1 is the recommended default for the MLX90640, not YOLO:**
YOLO's backbone downsamples through several stride-2 stages (typically
÷8, ÷16, ÷32 total). On a 32×24 input, a ÷32 stage collapses the image to
roughly 1×1 — there's no architecture-level way for a standard CNN detector
to do anything meaningful at that native resolution, regardless of
training. What DOES work at 768 total pixels — and is how most real
low-resolution thermal "presence" sensors operate — is much simpler:
threshold pixels in a plausible human temperature range and group them into
blobs. See `scripts/pixel_footprint_calculator.py` and
`scripts/simulate_mlx90640.py` for the concrete feasibility experiments —
run these BEFORE writing/training anything.

## Architecture

```
THERMAL FRAME (native 32x24 array, OR higher-res camera / video / live feed)
      |
PREPROCESSING (grayscale/radiometric handling; NO upscaling used for detection —
      |         upscaling is display-only, see simulate_mlx90640.py)
      v
HUMAN/BLOB DETECTOR  (Tier 1 classical, or Tier 2 YOLO — same output shape)
      |  -> list of Detection(x1,y1,x2,y2,confidence)
      v
MULTI-OBJECT TRACKER  (src/tracking/simple_tracker.py — ByteTrack-style
      |                 two-tier confidence matching + lost-track re-association)
      |  -> dict of {track_id: Track}, stable IDs across brief occlusion
      v
PER-PERSON MOVEMENT ESTIMATOR  (src/motion/movement_estimator.py — smoothed,
      |                         box-size-normalized centroid speed)
      v
MOTIONLESS TIMER / STATE MACHINE  (inside Track — accumulates stillness time
      |                            per person, with hysteresis on both ends)
      v
WARNING ENGINE  (src/warning/warning_engine.py — fires once per state
      |           transition, not every frame)
      v
DISPLAY + EVENT LOGGING  (color-coded overlay, console, CSV log, screenshot)
```

| Block | Input | Output | Trained? | Library |
|---|---|---|---|---|
| Detector | frame | list of person boxes + confidence | Tier 1: No. Tier 2: Yes | OpenCV (Tier 1) / Ultralytics (Tier 2) |
| Tracker | boxes + timestamp | per-person `Track` objects with stable IDs | No — geometric matching | stdlib + OpenCV |
| Movement estimator | a track's position history | normalized speed | No — pure math | stdlib |
| Motionless timer | speed + dt | accumulated stillness duration, warning flag | No — deterministic state machine | stdlib |
| Warning engine | tracks | trigger/clear events | No — rule-based | stdlib |
| Event logger | events + frame | CSV rows, screenshots | No | OpenCV, `csv` |

**Do you need ANY machine learning for "no movement" detection? No.**
Everything after the detector is a deterministic algorithm, not a trained
model — recommended deliberately: there isn't remotely enough labeled
"motionless for N minutes" thermal video to train a classifier on, and a
rule-based state machine is auditable ("the alert fired because normalized
speed stayed below 0.05 for 120 seconds" is a statement a rescuer or
auditor can check against the log; a learned "movement classifier" would
be an unexplainable black box for no accuracy benefit here).

## MLX90640 feasibility — the numbers, and what to test early

Run this first, before any other Stage 2/8 work:
```powershell
python scripts/pixel_footprint_calculator.py
```
This prints a table of expected person pixel footprint at various distances
for the MLX90640's two FOV variants. Concretely (standard 55°×35° FOV): a
standing person occupies roughly **110 px** (5×22) at 3m, shrinking to
**~28 px** (2.6×11) at 6m, and under **10 px** total by 10m — and at 1m a
standing person's height (65px) actually exceeds the sensor's 24-pixel
vertical resolution entirely (too close, gets clipped). **Note the distance
in this table where the footprint drops below ~2×2–3×3 px for your planned
deployment range — that's your early go/no-go signal**, before writing
more code. Cave/mine tunnels are often narrow, which works in this
sensor's favor (short expected encounter distances).

Then test on real(ish) data:
```powershell
python scripts/simulate_mlx90640.py --source path/to/any_thermal_video.mp4 --mode video
```
This downsamples existing footage to a genuine 32×24 array (via
area-averaging, simulating how a real low-resolution sensor's larger pixels
physically integrate heat — not just a naive resize) and runs the Tier 1
detector directly on it, so you can see with real footage whether detection
holds up before you own the hardware. **Upscaled output is for your eyes
only** — it contains no more information than the 32×24 array and must
never be used as the actual detection input.

**Radiometric advantage:** the MLX90640 outputs real °C per pixel, not
just relative brightness. Use `mode="radiometric"` in
`ClassicalBlobPersonDetector` once you have real sensor data — thresholding
on an absolute plausible skin/clothing temperature range (rather than "the
hottest N% of this frame") is more robust, particularly against a
uniformly warm or uniformly cool background (a real risk in an enclosed
mine/cave space) where relative/percentile thresholding can degrade — this
was an actual bug caught and fixed during development (see the strict `>`
vs `>=` comment in `classical_blob_detector.py`).

## Tracker choice: why ByteTrack's approach, not SORT or DeepSORT

- **DeepSORT** (SORT + a trained appearance re-identification CNN) —
  rejected. Appearance embeddings need real visual texture to be
  discriminative; a thermal blob, especially at 32×24, has essentially none
  — all warm blobs look alike to a re-ID model at that resolution. A second
  trained model for no real benefit.
- **SORT** (Kalman filter + IoU matching, no appearance model) — a
  reasonable simple baseline, but discards low-confidence detections
  outright, which loses track of a person during partial occlusion or a
  weak thermal signature — exactly the failure mode you're worried about.
- **ByteTrack** (SORT + a second matching pass that tries to rescue
  low-confidence detections against still-unmatched tracks) — **this
  project's approach.** Directly solves the occlusion/weak-signal problem,
  with no appearance model needed. `src/tracking/simple_tracker.py`
  implements this idea generically (so it works for both detector tiers,
  not just the YOLO path) plus a lost-track **re-association** step: a
  track that temporarily disappears keeps its ID and its accumulated
  motionless timer (frozen, not reset) for `lost_track_grace_period_sec`,
  and reappearing nearby reclaims the same identity instead of starting a
  new timer from zero.

(If you only ever use the Tier 2 YOLO path, Ultralytics' built-in
`model.track(tracker="bytetrack.yaml")` is an equally valid alternative to
`SimpleTracker` — the custom tracker here exists specifically so Tier 1
has the same capability without depending on Ultralytics.)

## Measuring "no movement" — what's actually computed, and why

Implemented in `src/motion/movement_estimator.py` / `src/tracking/track.py`:

- **Signal used: bounding-box centroid displacement**, smoothed over a
  trailing ~1 second window (`smoothing_window_sec`) and **normalized by
  the box's own diagonal** (not raw pixels), so the same physical movement
  registers similarly regardless of distance from the camera.
- **NOT optical flow** — at a handful of pixels per person, per-pixel flow
  has essentially no reliable signal, and is unjustified extra compute.
  Worth revisiting only if you later use a much higher-resolution camera
  and need to catch subtle movement (e.g. a twitching limb) that centroid
  tracking alone would miss.
- **NOT raw pixel/temperature change** as the movement signal, for the same
  low-resolution reasoning — thermal sensor noise alone can shift pixel
  values without anyone moving. (Radiometric temperature IS used for
  *detecting presence* in Tier 1, just not for detecting movement.)
- **Jitter rejection:** speed is computed from averaged clusters of samples
  at each end of the smoothing window (not two raw endpoint frames), and a
  track only counts as "moving" enough to reset the motionless clock after
  `movement_confirm_time_sec` of **sustained** above-threshold speed —
  hysteresis that stops one noisy frame from erasing minutes of
  accumulated stillness.
- **Camera movement:** the whole design assumes a static/fixed-mount
  camera (realistic for a monitoring point in a tunnel). A moving platform
  (drone, handheld) is out of scope for this version — global-motion
  compensation would need background feature tracking, real added
  complexity not justified unless you actually need a mobile platform.
- **All thresholds are configurable in `src/config.py`** and MUST be
  calibrated against real footage with `scripts/calibrate_thresholds.py` —
  the shipped defaults are starting points, not physically derived or
  medically meaningful constants.

## Time-based warning logic (the state machine)

Per-track states: `PENDING` → `ACTIVE` (moving or accumulating stillness) →
optionally `WARNING_ACTIVE` (folded into `Track.warning_active`) → `LOST`
(grace period, timer frozen) → `ENDED` (grace period expired).

Configurable parameters (`src/config.py`), with reasoning for each default
in the file itself:

| Parameter | Default | Purpose |
|---|---|---|
| `track_confirmation_time_sec` | 2.0s | A track must survive this long before it can ever reach a warning — filters one-frame false-positive blobs |
| `motion_threshold` | 0.05 (box-diagonals/sec) | Speed below this = "not moving" this instant |
| `movement_confirm_time_sec` | 2.0s | Sustained-movement requirement before the motionless clock resets (jitter rejection) |
| `motionless_time_sec` | 120s | Accumulated stillness needed to trigger a warning |
| `warning_clear_confirm_time_sec` | 5.0s | Sustained movement needed to CLEAR an active warning — deliberately slower than triggering, since a false "all clear" is worse than a lingering alert |
| `lost_track_grace_period_sec` | 12.0s | How long a track survives a detector dropout/occlusion before being retired |
| `reassociation_max_distance_frac` | 0.12 (of frame diagonal) | How close a reappearing detection must be to a recently-lost track to be treated as the same person |

## Multiple people

The tracker maintains one `Track` object (with its own history, timer, and
warning state) per person, keyed by track ID — every person is monitored
completely independently; `scripts/run_monitor.py` loops over all current
tracks every frame.

## Warning system — what's implemented, and build order

1. **Console message** — implemented, always on (`EventLogger.log`)
2. **Timestamped CSV event log** — implemented (`outputs/events/event_log.csv`)
3. **On-screen bounding-box color coding** — implemented in
   `scripts/run_monitor.py` (green = moving, yellow = accumulating
   stillness, red = warning active, gray = unconfirmed)
4. **Saved event screenshot** — implemented, saved on every TRIGGERED event
5. **Sound** — NOT implemented by default (see note in `event_logger.py`):
   needs a real decision about where audio should play (at the sensor?
   at a remote operator's station, which implies networking?) that
   shouldn't be baked in before you know the deployment shape.

## Dataset strategy (revised — no posture data needed)

**A. Human detection data (Tier 2 / YOLO only)** — same public thermal
bounding-box datasets as before (Roboflow thermal set, FLIR ADAS, LLVIP,
KAIST, WiSARD — see `scripts/download_dataset.py` and
`src/preprocessing/prepare_dataset.py`). Not needed at all if you go
straight to Tier 1 for the MLX90640.

**B. Motion/no-motion "data"** — this does **not** need frame-level
labeled datasets, because movement is *computed* by the tracker
(algorithm), not learned. What's actually needed is a small number of
**self-recorded** calibration clips — a person standing/sitting still for
a minute or two, and a person walking normally — used to pick
`motion_threshold` with `scripts/calibrate_thresholds.py`. Public datasets
can't substitute for this: no dataset captures "a person remains still for
3 minutes in a mine-like setting", and that's exactly the behavior this
system needs to be tuned against.

**Realistic data volumes:**

| Purpose | What's needed | Roughly how much |
|---|---|---|
| Detector training (Tier 2 only) | Thermal images + person boxes | Hundreds to low-thousands (transfer learning) |
| Tracker testing | A few multi-person video clips w/ occlusion | A handful of clips |
| Motion-threshold calibration | Self-recorded still + walking clips | 2-10 short clips, ideally at your real deployment distances |
| Warning-system testing | Same calibration clips | Same as above |

## Implementation roadmap (VS Code, from zero)

| Stage | Goal | Key files | Test before moving on |
|---|---|---|---|
| 1 | Dataset + human detection on thermal images (Tier 2) | `scripts/download_dataset.py`, `scripts/train.py`, `scripts/validate.py`, `scripts/predict.py` | `mAP50 > 0.7` on held-out test |
| 2 | Test detector under low-res/downsampled conditions | `scripts/pixel_footprint_calculator.py`, `scripts/simulate_mlx90640.py` | Can you still see/detect a person-sized blob after downsampling to 32×24? |
| 3 | Thermal video + human detection | `src/inference/predict_image.py`, `scripts/run_monitor.py --detector blob` (or `yolo`) on a video, no tracking/warning logic exercised yet beyond pass-through | Boxes appear on a real/synthetic video |
| 4 | Add tracking | `src/tracking/track.py`, `src/tracking/simple_tracker.py` | Same person keeps the same ID across a clip; ID survives a brief occlusion (test script pattern shown below) |
| 5 | Add movement measurement | `src/motion/movement_estimator.py` | A walking test clip shows clearly higher speed than a still test clip |
| 6 | Add motionless timer + calibrate | `src/config.py`, `scripts/calibrate_thresholds.py` | Timer accumulates correctly on a still clip, resets correctly on a walking clip |
| 7 | Add warnings/event logging | `src/warning/warning_engine.py`, `src/warning/event_logger.py`, `scripts/run_monitor.py` | Warning fires at roughly the expected time on a staged "goes still" clip, logs to CSV + screenshot, clears when movement resumes |
| 8 | Test using MLX90640-like 32×24 data | `scripts/simulate_mlx90640.py` on your Stage 3-7 test clips | Full detect→track→warn pipeline still functions end-to-end on downsampled footage |
| 9 | Connect actual MLX90640 hardware | New: a small adapter reading the sensor (I2C, typically via a microcontroller bridging to USB/serial, or direct I2C on a Jetson/Pi) that produces a 24×32 numpy array per frame, fed into the SAME `ClassicalBlobPersonDetector.detect()` | Live warning fires when you deliberately stand still in front of the real sensor |

## Setup

```powershell
python -m venv venv
venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121   # or /cpu — only needed for Tier 2 (YOLO)
pip install -r requirements.txt
python tests/test_environment.py
```

Note: **Tiers 1 pipeline (blob detector, tracker, motion, warning, event
logging) needs only OpenCV + NumPy** — no torch/ultralytics install
required at all if you're going straight for the MLX90640 path. Skip the
torch install and the `[FAIL] import torch` line in
`tests/test_environment.py` if so; only Tier 2 (YOLO) needs it.

## Quickstart — Tier 1 (MLX90640-oriented), no dataset needed

```powershell
python scripts/pixel_footprint_calculator.py
python scripts/simulate_mlx90640.py --source path\to\any_thermal_video.mp4 --mode video
python scripts/run_monitor.py --source path\to\any_thermal_video.mp4 --detector blob
```

## Quickstart — Tier 2 (YOLO, higher-res camera)

```powershell
$env:ROBOFLOW_API_KEY = "your_key_here"
python scripts/download_dataset.py
# edit data/dataset.yaml `path:` to point at the downloaded dataset
python scripts/train.py --data data/dataset.yaml --epochs 60
python scripts/validate.py --weights outputs/runs/detect/stage1_person_detector/weights/best.pt
python scripts/run_monitor.py --source path\to\video.mp4 --detector yolo --weights outputs/runs/detect/stage1_person_detector/weights/best.pt
```

## Project structure

```
thermal-human-detection/
├── data/                       # (Tier 2 only) thermal detection datasets
├── models/                       # optional long-term checkpoint storage
├── src/
│   ├── config.py                   # every tunable parameter, documented
│   ├── detection/
│   │   ├── base.py                    # shared Detection + PersonDetector interface
│   │   ├── classical_blob_detector.py # Tier 1 — MLX90640-native, no training
│   │   └── yolo_detector.py           # Tier 2 — trained YOLO wrapper
│   ├── tracking/
│   │   ├── track.py                    # per-person state: history, motionless timer
│   │   └── simple_tracker.py           # ByteTrack-style matching + re-association
│   ├── motion/
│   │   └── movement_estimator.py       # normalized-speed calculation
│   ├── warning/
│   │   ├── warning_engine.py           # trigger/clear event detection
│   │   └── event_logger.py             # CSV log + screenshots
│   ├── preprocessing/
│   │   └── prepare_dataset.py          # (Tier 2) dataset split + format conversion
│   └── inference/
│       └── predict_image.py            # (Tier 2) single-image YOLO helper
├── scripts/
│   ├── download_dataset.py           # (Tier 2) pull a thermal dataset from Roboflow
│   ├── train.py / validate.py / predict.py   # (Tier 2) YOLO training pipeline
│   ├── pixel_footprint_calculator.py # MLX90640 feasibility math — run FIRST
│   ├── simulate_mlx90640.py          # downsample real footage to 32x24, test detection
│   ├── calibrate_thresholds.py       # pick motion_threshold from real footage
│   └── run_monitor.py                # MAIN pipeline: detect->track->warn, any video/camera
├── tests/
│   └── test_environment.py
├── outputs/
│   ├── runs/                        # (Tier 2) Ultralytics training logs/weights
│   ├── predictions/                 # annotated images/videos
│   ├── calibration/                 # speed logs from calibrate_thresholds.py
│   └── events/                      # event_log.csv + screenshots/
├── requirements.txt
└── README.md
```

## Common mistakes / troubleshooting

- **Zero detections on a video you know has a person** — for the blob
  detector, check `mode` matches your data (`relative` for ordinary 0-255
  footage, `radiometric` only for real °C data) and try a lower
  `--blob_percentile` (e.g. 85) if the person occupies more than ~10% of
  the frame, or higher (e.g. 97) if they occupy much less — percentile
  needs to roughly match the fraction of the frame the person actually
  covers. Sanity-check on a single frame with
  `ClassicalBlobPersonDetector.detect()` directly before debugging a whole video.
- **A confirmed track never reaches ACTIVE / timer never starts** —
  remember `track_confirmation_time_sec` (default 2s) delays the start of
  motionless-time accumulation; make sure your test clip's still period is
  comfortably longer than `track_confirmation_time_sec + motionless_time_sec`.
- **Track ID keeps changing for the same person** — lower
  `min_match_iou`, raise `reassociation_max_distance_frac`, or raise
  `lost_track_grace_period_sec` if your detector has frequent brief dropouts.
- **Warning won't clear even though the person is clearly moving** — check
  `warning_clear_confirm_time_sec` (default 5s) — it's intentionally slower
  to clear than to trigger; this is by design, not a bug, but tune it down
  if it's too conservative for your testing.
- **`ModuleNotFoundError: No module named 'src'`** — run scripts from the
  project root, not from inside `scripts/`.
