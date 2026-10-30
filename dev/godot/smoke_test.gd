# Godot 4 smoke test for engine/godot/sprite_frames.tres. Run through dev/godot_smoke.py, which
# builds the project; by hand:
#   godot --headless --path <project> --script res://smoke_test.gd --fixed-fps 60 -- <set dir> 60
# 1. Loads the SpriteFrames as the editor imported it, and checks every clip's frame count, fps
#    and loop flag against animations.json.
# 2. Rebuilds every frame from the imported atlas texture (region + margin, as AtlasTexture
#    draws it) and compares it with the source PNG.
# 3. Plays clips on an AnimatedSprite2D at the fixed tick rate and checks the frame sequence,
#    how long each frame stays up, loop wrap and animation_finished.
# Prints one "FAIL ..." line per problem and "RESULT ok|fail"; exits 1 on failure.
extends SceneTree

var fails := []
var doc := {}
var sprite: AnimatedSprite2D
var queue := []
var cur := ""
var shown := []
var finished := false
var ticks := 0
var hz := 60


func fail(msg: String) -> void:
	fails.append(msg)
	print("FAIL ", msg)


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var set_dir: String = args[0]
	hz = int(args[1])     # must match --fixed-fps; each tick then advances exactly 1/hz s
	doc = JSON.parse_string(FileAccess.get_file_as_string(set_dir.path_join("animations.json")))
	var sf: SpriteFrames = load("res://sprite_frames.tres")
	if sf == null:
		fail("sprite_frames.tres did not load")
		finish()
		return
	check_frames(sf, set_dir)
	sprite = AnimatedSprite2D.new()
	sprite.sprite_frames = sf
	sprite.animation_finished.connect(func(): finished = true)
	root.add_child(sprite)
	# A looping and a one-shot clip at each fps the set uses.
	var picked := {}
	for name in doc.clips:
		var c: Dictionary = doc.clips[name]
		var key := "%s_%s" % [c.fps, c.loop]
		if (args.size() > 2 and args[2] == "all") or not picked.has(key):
			picked[key] = name
			queue.append(name)
	start_next()


func check_frames(sf: SpriteFrames, set_dir: String) -> void:
	var size := int(doc.frame_size)
	var pages := {}
	var checked := 0
	var worst := 0.0
	for name in doc.clips:
		var c: Dictionary = doc.clips[name]
		var n: int = c.frames.size()
		if not sf.has_animation(name):
			fail("%s: missing animation" % name)
			continue
		if sf.get_frame_count(name) != n:
			fail("%s: %d frames, manifest has %d" % [name, sf.get_frame_count(name), n])
		if not is_equal_approx(sf.get_animation_speed(name), float(c.fps)):
			fail("%s: speed %s, manifest fps %s" % [name, sf.get_animation_speed(name), c.fps])
		if sf.get_animation_loop(name) != bool(c.loop):
			fail("%s: loop %s, manifest %s" % [name, sf.get_animation_loop(name), c.loop])
		for i in min(n, sf.get_frame_count(name)):
			var t := sf.get_frame_texture(name, i) as AtlasTexture
			if t == null or t.atlas == null:
				fail("%s#%d: not an AtlasTexture with an atlas" % [name, i])
				continue
			if t.get_width() != size or t.get_height() != size:
				fail("%s#%d: %dx%d, frame size %d" % [name, i, t.get_width(), t.get_height(), size])
			var key := t.atlas.resource_path
			if not pages.has(key):
				var im := t.atlas.get_image()
				if im == null:
					fail("%s: imported texture has no image data" % key)
					return
				im.decompress()
				im.convert(Image.FORMAT_RGBA8)
				pages[key] = im
			var got := Image.create(size, size, false, Image.FORMAT_RGBA8)
			got.blit_rect(pages[key], Rect2i(t.region), Vector2i(t.margin.position))
			var want := Image.load_from_file(set_dir.path_join("frames/%s/%s_%03d.png" % [name, name, i]))
			want.convert(Image.FORMAT_RGBA8)
			# Compare premultiplied: transparent pixels carry bled colour in the atlas. With the
			# exported .import settings the import is lossless, so anything else must match exactly.
			got.premultiply_alpha()
			want.premultiply_alpha()
			if got.get_data() != want.get_data():
				var err: float = got.compute_image_metrics(want, false)["max"]
				worst = maxf(worst, err)
				fail("%s#%d: pixels differ from the source frame (max error %d)" % [name, i, err])
			checked += 1
	print("frames checked: %d, max error %d" % [checked, worst])


func start_next() -> void:
	if queue.is_empty():
		finish()
		return
	cur = queue.pop_front()
	shown = []
	finished = false
	ticks = 0
	sprite.play(cur)


func _process(_delta: float) -> bool:
	if cur == "":
		return true
	shown.append(sprite.frame)
	ticks += 1
	var c: Dictionary = doc.clips[cur]
	var n: int = c.frames.size()
	var span: int = ceili(float(hz) * n / float(c.fps))
	if ticks >= (2 * span + 4 if c.loop else span + 2 * hz / int(c.fps) + 4):
		judge(cur, c, n)
		start_next()
	return cur == "" and queue.is_empty()


func judge(name: String, c: Dictionary, n: int) -> void:
	var per: float = float(hz) / float(c.fps)
	var runs := []
	for f in shown:
		if runs.is_empty() or runs[-1][0] != f:
			runs.append([f, 1])
		else:
			runs[-1][1] += 1
	for k in runs.size():
		var want: int = k % n if c.loop else mini(k, n - 1)
		if runs[k][0] != want:
			fail("%s @%dHz: frame order %s" % [name, hz, runs.map(func(r): return r[0])])
			return
		var inner: bool = k > 0 and k < runs.size() - 1
		if inner and abs(runs[k][1] - per) > 1.0:
			fail("%s @%dHz: frame %d held %d ticks, expected %.1f" % [name, hz, runs[k][0], runs[k][1], per])
	if c.loop and finished:
		fail("%s: looping clip emitted animation_finished" % name)
	if not c.loop and not finished:
		fail("%s: one-shot clip never emitted animation_finished" % name)
	print("played %s @%dHz: %d frames, loop=%s, %d ticks" % [name, hz, n, c.loop, ticks])


func finish() -> void:
	print("RESULT ", "ok" if fails.is_empty() else "fail")
	quit(0 if fails.is_empty() else 1)
