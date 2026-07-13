This folder holds test audio clips (stutter, mixed-language, noisy) once
someone can record them. Until then, `MockASRBackend` reads a `.txt`
transcript with the same base name instead of an actual audio file (see
`example1.txt`), so the rest of the pipeline can be built and tested without
a microphone.

Before the event, replace these with a few real recordings and drop
matching filenames in (e.g. `stutter1.wav`), then switch `ASR_BACKEND` to
`local` or `event` to use real transcription instead of the mock.
