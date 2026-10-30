const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
(async()=>{
 const root=path.resolve(process.argv[2]),browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined});
 try{
  const page=await browser.newPage({viewport:{width:1150,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://localhost/**',r=>{const file=path.resolve(root,'.'+new URL(r.request().url()).pathname);if(!file.startsWith(root+path.sep))return r.fulfill({status:404,body:''});return r.fulfill({contentType:'text/html',body:fs.readFileSync(file)});});
  await page.goto('http://localhost/preview.html');await page.waitForFunction(()=>!!window.__demo);
  assert.equal(await page.locator('#gallery canvas').count(),7);
  await page.keyboard.down('KeyD');await page.waitForFunction(()=>__demo.controller.player.name==='walk'&&__demo.controller.x>512);
  await page.keyboard.up('KeyD');await page.waitForFunction(()=>__demo.controller.player.name==='idle');
  await page.keyboard.press('Digit2');await page.keyboard.down('KeyA');await page.waitForFunction(()=>__demo.controller.player.name==='trot'&&__demo.controller.flip);
  await page.keyboard.down('ShiftLeft');await page.waitForFunction(()=>__demo.controller.player.name==='run');
  await page.keyboard.up('KeyA');await page.keyboard.up('ShiftLeft');await page.waitForFunction(()=>__demo.controller.player.name==='idle');
  await page.evaluate(()=>{__demo.controller.x=700;__demo.controller.flip=false;});
  await page.keyboard.press('KeyJ');await page.waitForFunction(()=>__demo.controller.player.name==='attack');
  await page.waitForFunction(()=>__demo.controller.player.name==='idle');
  assert.equal(await page.evaluate(()=>__demo.hits),1);
  await page.keyboard.press('KeyH');await page.waitForFunction(()=>__demo.controller.player.name==='hurt');
  await page.waitForFunction(()=>__demo.controller.player.name==='idle');
  await page.keyboard.press('KeyX');await page.waitForFunction(()=>__demo.controller.player.name==='death'&&__demo.controller.player.done);
  await page.keyboard.press('KeyX');await page.waitForFunction(()=>__demo.controller.player.name==='idle');
  assert.deepEqual(errors,[]);
  await page.screenshot({path:process.argv[3]||'/tmp/quadruped-browser.png',fullPage:true});
  console.log('quadruped preview: four galleries, walk/trot/run, left/right and stop OK');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
