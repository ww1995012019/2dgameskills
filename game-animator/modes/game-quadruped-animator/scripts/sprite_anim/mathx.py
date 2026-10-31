"""Use a shared sprite module from the unified bundle."""
from pathlib import Path as _Path

_source = (_Path(__file__).resolve().parents[3] / "game-sprite-animator" /
           "scripts" / "sprite_anim" / _Path(__file__).name)
exec(compile(_source.read_bytes(), str(_source), "exec"), globals())
del _source, _Path
