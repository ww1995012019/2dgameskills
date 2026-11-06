# Windows counterpart of regress_all.sh for the side-view sprite and shooter sets.
# Run from anywhere; it uses the unified bundle (game-animator/modes/) as the source.
# Results land in %TEMP%\spr\all.
$root = (Resolve-Path "$PSScriptRoot\..").Path
$out = "$env:TEMP\spr\all"
Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
$sets = @(
  @{ mode = 'game-sprite-animator'; chars = 'hero','knight','mage','ninja','goblin' },
  @{ mode = 'game-shooter-animator'; chars = 'commando','swat','ghost','mercenary' }
)
foreach ($s in $sets) {
  $m = "$root\game-animator\modes\$($s.mode)"
  foreach ($c in $s.chars) {
    foreach ($p in 'hd','pixel') {
      $d = "$out\$c-$p"
      python "$m\scripts\generate.py" --character "$m\assets\characters\$c.json" --preset $p --out $d 2>&1 | Select-String -Pattern '\[done\] \d|Traceback|Error'
      python "$m\scripts\qa_motion.py" $d 2>&1 | Select-String -Pattern ' FAIL | WARN |result:|Traceback'
    }
  }
}
"ALL DONE"
