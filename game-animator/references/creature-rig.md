# Experimental creature rig

This is an experimental side-view rigid-part flight workflow, not a finished bird, bat or dragon
product. It accepts a bone configuration and per-bone PNGs, generates six types of motion and
sprite exports, and checks several numeric invariants. Shape quality, anatomy, occlusion, collision
and suitability for a specific game still require visual review. The bundled example uses coloured
bone strokes as placeholders, not finished animal art.

The `flight_bird_skeleton.json`, `flight_bat_skeleton.json` and `flight_dragon_skeleton.json`
examples exercise different parameters and wing segment counts using the same code. They are line
skeletons for testing configuration, not anatomically validated or finished species artwork.

```bash
python scripts/generate_creature.py --config assets/creatures/flight_example.json --size 256 --fps 15 --out out/flight
python scripts/qa_creature.py out/flight
```

`--out` must be a new or empty directory. Open `preview.html` to play and switch clips; this preview
does not simulate game movement or collision. The generator emits frames, sheets, an atlas and
metadata, plus Godot, Cocos and web files. These new-mode files have structural tests only; they have
not been imported or played in those engines.
The generator refuses requests above 512 frames or 512 MiB of uncompressed frame data; reduce the
size, FPS, period or selected clips to fit.

The configuration has one rooted `bones` tree and optional `motion` parameters. Each bone has a
unique `name`, `parent` (null for the single root), positive `length`, local rest `angle` in
degrees, optional local angle `limits`, `tags`, local `offset`, and an `anchor` of `start` or
`end` on its parent. Angles and offsets use x-right, y-down coordinates. Any bone can specify
`flap_amplitude` and `flap_phase`; the full amplitude must fit its local limits. Lengths remain
fixed, and missing parents, cycles, non-finite values and impossible amplitudes are rejected.

`CreatureRig(spec).pose(time_seconds, action)` returns each bone's start, end and absolute angle.
`flap`, `hover` and `glide` loop; `dive`, `hurt` and `fall` stop at the end of the configured
period. `motion.period`, `motion.bob` and `motion.pitch` control timing and body motion. Body
translations and rotations are local poses, not game-world physics or autonomous movement.

`parts` maps bone names to PNG `image`, source-pixel `pivot`, and source `pixels_per_unit`; paths
are relative to the JSON file. Source parts must be authored pointing along +x. Omitted parts are
rendered as coloured placeholder strokes (`color` and rig-unit `width`). `draw_order` lists every
bone once, back to front. `view.units` determines the visible rig-unit width and `view.pivot` is a
normalized canvas position. Rig art is rigidly rotated; hidden or missing surfaces need new art.

`wing_pairs` optionally names pairs with matching local joint angles. QA checks these explicit pairs
within two degrees, bone lengths and attachments, joint limits, abrupt endpoint movement, loop endpoints,
frame times, frame-to-trace pixel hashes, atlas-to-frame reconstruction and frame-edge contact;
it does not infer anatomical symmetry. Do not declare a pair for a deliberately asymmetric rig.
Tests inject geometry, wing-phase, loop and frame-boundary faults, but cannot prove visual quality.
