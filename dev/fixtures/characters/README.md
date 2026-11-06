# Real-character fixtures

Each folder is one real AI-art character the user has looked at, managed by `dev/real_characters.py`:

- `input/`: the reviewed job (job.json, source, reference, layers, hand hints, reviews, rig/) or a
  character folder, copied without build outputs. Rendering goes through the normal generate.py gates.
- `fixture.json`: clips and generate.py arguments, and once the user approved the moving result,
  who approved it, when, and the RGBA hash of every approved frame.
- `approved/`: the approved build's `animations.json` and atlas, used as the "before" side of the
  comparison GIFs.

`python dev/real_characters.py check` is part of the full verification. A changed approved frame
fails the check until the user has seen `check --compare` GIFs and accepted the new frames; then run
`approve` with the new build. Never re-approve without the user's verdict.
