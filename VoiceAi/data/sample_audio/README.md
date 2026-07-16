Test audio clips (stutter, mixed-language, noisy) go here once someone can
record them on the lab laptop mic. Until then, `MockASRBackend` reads a
`.txt` transcript with the same base name instead of an actual audio file
(see `example1.txt`), so the rest of the pipeline is testable without a
microphone.

Before the event: record real clips, drop matching filenames in (e.g.
`stutter1.wav`), then set `ASR_BACKEND=local` or `event` in `.env`.
