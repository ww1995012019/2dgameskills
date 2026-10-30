# Run from game-shooter-animator/scripts. Results land in %TEMP%\spr\all.
$a = (Resolve-Path ..\..\game-sprite-animator).Path
$out = "$env:TEMP\spr\all"
Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
foreach ($c in 'hero','knight','mage','ninja','goblin') {
  foreach ($p in 'hd','pixel') {
    $d = "$out\$c-$p"
    python "$a\scripts\generate.py" --character "$a\assets\characters\$c.json" --preset $p --out $d 2>&1 | Select-String -Pattern '\[done\] \d|Traceback|Error'
    python "$a\scripts\qa_motion.py" $d 2>&1 | Select-String -Pattern ' FAIL | WARN |result:|Traceback'
  }
}
foreach ($c in 'commando','swat','ghost','mercenary') {
  foreach ($p in 'hd','pixel') {
    $d = "$out\$c-$p"
    python generate.py --character ..\assets\characters\$c.json --preset $p --out $d 2>&1 | Select-String -Pattern '\[done\] \d|Traceback|Error'
    python qa_motion.py $d 2>&1 | Select-String -Pattern ' FAIL | WARN |result:|Traceback'
  }
}
"ALL DONE"
