# Character puppet handover (2026-11-03)

This note is for the next AI continuing the user's wuxia character and reusable character workflow. Read this before regenerating art or editing the current case. The repository's general handover remains in [`../../HANDOVER.md`](../../HANDOVER.md); implementation roadmap is [`../roadmap.md`](../roadmap.md).

## Current state

- Repository: `/workspace/2dgameskills`, branch `work`, based on `c019f1f` (the then-current `origin/main`). The current working tree contains the whole ongoing workflow/validator/runtime change; do not discard it.
- The user's current artwork and all generated case evidence live outside git at `/workspace/2dgameskills-output/wuxia-template-v1/full_character`. They may not exist in a fresh clone. Do not claim the uploaded original image bytes are archived: they are not.
- Static character: the user rejected a narrow/flat head, then approved the repaired static head and full-body appearance with “可以 没问题”. Approval is hash-bound in `static_user_approval.json`. The rejected image and evidence are retained in `review_history/head_rejected_by_user/`. This approval is for static appearance only.
- Motion: a measured eight-layer rig now exists at `motion_v3/rig`; idle and walk are rendered, and their quantitative QA passes. `motion_v3/preview.html`, `idle.gif`, and `walk.gif` are for the user to review. The motion visual report/approval is deliberately pending. Do not call this final pass or expand to the other 25 clips before the user has reviewed these two.
- The 26-character legacy regression completed: all 26 returned 0 FAIL. `cutout_demo-pixel` still has 7 WARN and `cutout_demo-hd` 8 WARN; the other 24 are 0 WARN. These are existing demo warnings, not failures in the wuxia case.
- Full `dev/tests` unittest discovery is still running in the current environment (PID 27836 when this note was written); its log is `/tmp/template-binding-full-tests.log`. Wait for its final summary/exit status before reporting the complete test suite. The focused binding tests previously passed; see `/tmp/template-bind-tests-final.log` and this session's log for the latest added test.
- `git diff --check` passed before this handover edit. The changes have not yet been committed, pushed, or merged when this note is first written; update this line and the general handover after doing so.

## What changed in the repository

The repository now has a staged character workflow in `game-sprite-animator/scripts/character_workflow.py` and `references/basic-character-workflow.md`, synchronized into the unified `game-animator` package and the standalone `.skill` bundles. It supplies fixed prompts and phase gates for reference review, isolated parts, measured two-hand/weapon contact, binding, preview, and visual approval. The reference gate now asks an actual reviewer to assess side view, occlusion, limbs, and equipment; it does not pretend simple background/height checks understand anatomy. The motion visual gate requires six explicit visual checks, treats structural defects as blockers, and ties each review to exact frames and evidence. Read `docs/roadmap.md` and the recent entries at the top of `HANDOVER.md` for the broader development history and limitations.

The real-case tools under `dev/template_*.py` implement registration, constrained repair, full static assembly, reference-derived head proportions, binding, and an offline motion preview. They are development tools, not an enabled default production path. Their tests include synthetic bodies and fault injection; those do not count as multiple real AI characters or prove AI drawing quality.

Production runtime changes in the three animator copies and `shared/` add optional measured weapon-grip offsets, measured boot sole contacts, and continuous walk support height from the two rolling foot targets. With no measurements, the previous grip and foot defaults remain in effect. `references/layered-art.md` documents the rules. Keep copies synchronized with the existing sync scripts and rebuild all three `.skill` archives if changing shared runtime/workflow files.

## Real case and the head issue

The first isolated head had a flat/narrow skull. That was a drawing/prompt failure, not an assembly scale bug. The third head was redrawn against a same-identity head crop, then attached without allowing collar width to enlarge the skull. The output aspect differs from the reference by about 1%; the earlier rejected head differed by about 46.6%. These ratios reject gross distortion, but cannot judge face identity or artistic quality. The repaired head and complete static character were explicitly accepted by the user. Keep the rejected image/report in history; do not overwrite the user's rejection or silently treat it as a motion approval.

The eight-layer static image includes near/far arms, near/far legs, hips, torso, head, and one sword. Existing source art and generation ledger are in the external case folder. The original uploaded image bytes were not archived, so provenance points to an approved generated side-view adaptation rather than the original upload.

## Binding and motion v3

`dev/template_binding.py` exports measured joints into the existing human puppet runtime. It reuses `lp.write_binding`, records per-layer hashes and input approval, measures ground sole points and the sword grip, and adjusts the mirrored far arm's resting elbow bend while preserving its source endpoints. Binding is under `motion_v3/rig/`; v2 is an archived attempt. Do not replace v3 with v2.

The runtime binding change threads optional measurements through skeleton geometry, weapon rendering/collision, sole rolling, foot traces, and ground constraints. `measured_walk_height()` uses a smooth minimum of the two rolling sole support targets. It only activates when both feet have measured contacts, allowing the pelvis to vault over stance support rather than forcing large boots into a deep crouch. Defaults remain unchanged for legacy characters. The current character's walk measures planted knee angle 28.27 degrees, mean foot slide 0.004 px, and maximum measured hover 0.19 px. These are numeric checks only.

The v3 export contains 72 idle frames (2.4 s) and 25 walk frames (0.84 s), both 30 fps. `qa_report.json` reports 0 FAIL/0 WARN for both. This is two of the existing 27 clips, not the full animation set. A packed sprite sheet warning in `generate.py` about the tall idle sheet is non-fatal; the atlas and frames were produced. The report and frames are in `motion_v3/build/`.

The production visual-review builder has also created four sheets at `motion_v3/build/review/`: `sheet_00.png`, `joints_00.png`, `shoulders_00.png`, and `arms_00.png`. They are evidence for review only; no verdict was recorded. The generic reviewer script displays several crops at high magnification, so inspect individual regions if a crop looks ambiguous. The latest case preview is `motion_v3/preview.html`; GIFs are adjacent. A preview-builder provenance file records the hashes and explicitly keeps `user_motion_approval=pending`, `final_visual_pass=false`, `engine_playback=false`.

## What to do next

1. Check the unittest process/log for its final exit status and test counts. Rerun only if it failed for an actionable reason. Run `git diff --check` and confirm synchronized runtime copies and `.skill` bundles are consistent.
2. Give the user the `motion_v3/preview.html` and GIFs and ask for feedback on both idle and walk. Do not turn a numerical pass or an AI visual glance into the user's approval. If they request a fix, preserve the old render/review and regenerate a version with fresh provenance and QA.
3. After both motions are accepted, save a hash-bound motion approval and update status without altering the earlier static approval. Then proceed to remaining requested actions in small reviewable batches, keeping visual and numeric QA separate. Do not generate all 27 just because the old runtime supports them.
4. If the external case assets are missing in the next environment, stop before binding or motion review and restore the case artifacts from the same workspace/backup. Git alone does not contain the generated character art, rendered frames, preview, or their approval record.

Useful commands (from repository root):

```bash
PYTHONPATH=dev/tests python -m unittest test_template_binding -v
JOBS=2 bash dev/regress_all.sh
python game-sprite-animator/scripts/visual_review.py /workspace/2dgameskills-output/wuxia-template-v1/full_character/motion_v3/build
```

The unittest discovery launched in this session uses writable temporary XDG paths and Chromium:

```bash
XDG_DATA_HOME=/tmp/template-binding-xdg/data \
XDG_CACHE_HOME=/tmp/template-binding-xdg/cache \
XDG_CONFIG_HOME=/tmp/template-binding-xdg/config \
CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium \
python -m unittest discover -s dev/tests -v
```

## Publication state

User asked to push and merge to `main`. At the beginning of this work, local `work` and `origin/main` both pointed at `c019f1f`. GitHub CLI reported that the configured `GH_TOKEN` is invalid. Finish the local commit and attempt the authorized push; if GitHub rejects authentication, leave the commit on `work` and report its hash and the exact credential problem. Do not rewrite `main` or force push.
