#!/usr/bin/env bash
# Downloads the official Godot 4.3 Linux build into dev/engines/godot/ for dev/godot_smoke.py.
# On macOS or Windows install Godot 4.3 yourself and set GODOT to the binary.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$here/godot"
cd "$here/godot"
curl -sSL -o godot.zip https://github.com/godotengine/godot/releases/download/4.3-stable/Godot_v4.3-stable_linux.x86_64.zip
unzip -qo godot.zip && rm godot.zip
"$here/godot/Godot_v4.3-stable_linux.x86_64" --headless --version
