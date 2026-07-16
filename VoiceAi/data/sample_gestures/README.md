Test gesture images go here once someone can capture them on the lab
laptop webcam. Until then, `MockVisionBackend` reads a `.json` sidecar
file with the same base name instead of an actual image (see
`thumbs_up.json`), so the rest of the pipeline is testable without a
camera.

Before the event: capture real photos of each predefined gesture
(thumbs_up, open_palm, fist, pointing, peace), drop matching filenames in
(e.g. `thumbs_up.jpg`), then set `VISION_BACKEND=local` in `.env` to use
real MediaPipe Hands detection instead of the mock.
