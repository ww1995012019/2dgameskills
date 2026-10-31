"""Weapon data. Gun frame: origin at the near-hand grip, +x along the barrel, +y up.

butt    rear end of the gun along the barrel, for clipping checks
hold    grip position from the near shoulder
fore    far-hand position from the grip
muzzle  bullet spawn point; exported per frame so shots leave the barrel on every aim angle
port    shell ejection port
well    where the magazine (or round) goes in
period  seconds per shot; rounded to whole frames at render time
"""

GUN_SCALE = 1.18      # guns read better slightly oversized on a chibi body

WEAPONS = {
    "pistol": dict(butt=-4, hold=(22, -2), fore=(0.8, -0.8), muzzle=(14.5, 5.8), port=(3, 7.5), well=(-0.5, -4),
                   period=0.2, kick=3.0, climb=7, flash=0.7, reload=1.1, kind="mag", shell=0.7),
    "smg": dict(butt=-15, hold=(8, -6.5), fore=(10.5, 1.5), muzzle=(21, 5.6), port=(3, 8), well=(5, -1),
                period=0.075, kick=1.3, climb=1.6, flash=0.75, reload=1.4, kind="mag", shell=0.8),
    "rifle": dict(butt=-20, hold=(6, -7), fore=(15, 1.5), muzzle=(35.5, 5.6), port=(1, 8), well=(6.5, -1),
                  period=0.1, kick=1.8, climb=1.8, flash=1.0, reload=1.7, kind="mag", shell=1.0),
    "shotgun": dict(butt=-21, hold=(6, -7), fore=(16, 1.2), muzzle=(37.5, 5.8), port=(2, 8), well=(8, 0.5),
                    period=0.7, kick=4.5, climb=7, flash=1.15, reload=1.9, kind="tube", shell=1.5),
    "sniper": dict(butt=-23, clear=11, hold=(7, -9), fore=(16, 1.5), muzzle=(53, 5.6), port=(0, 8), well=(5, -1),
                   period=1.15, kick=5.0, climb=6, flash=1.1, reload=2.0, kind="bolt", shell=1.3),
    "rocket": dict(butt=-28, hold=(3, -9), fore=(12, 1.2), muzzle=(39, 6), port=(-27, 6), well=(38, 6),
                   period=1.5, kick=5.5, climb=4, flash=1.1, reload=2.0, kind="rocket", shell=0.0),
}

SWAY_FLASH = (1.0, 0.55, 0.0)       # flash brightness on the frames after a shot


def shot_frames(weapon, fps):
    """Fire rate must land on whole frames, or the flash is missed on some shots and the
    gun appears to stutter even though the animation is correct."""
    return max(2, int(round(WEAPONS[weapon]["period"] * fps)))
