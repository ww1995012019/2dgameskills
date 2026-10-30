// Real browser smoke test for the self-contained gallery and free-movement preview.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
(async()=>{
 const root=path.resolve(process.argv[2]);const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined});
 try{
  const page=await browser.newPage({viewport:{width:1200,height:950}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://localhost/**',r=>{const file=path.resolve(root,'.'+new URL(r.request().url()).pathname);if(!file.startsWith(root+path.sep))return r.fulfill({status:404,body:''});return r.fulfill({contentType:'text/html',body:fs.readFileSync(file)});});
  await page.goto('http://localhost/preview.html');await page.waitForFunction(()=>!!window.__demo);
  assert.equal(await page.locator('#gallery canvas').count(),8);
  await page.locator('button[data-action="death"]').click();assert.equal(await page.locator('#gallery canvas').count(),8);
  await page.keyboard.down('KeyW');await page.keyboard.down('KeyD');await page.waitForFunction(()=>__demo.controller.action==='walk'&&__demo.controller.direction==='up_right'&&__demo.controller.x>560&&__demo.controller.y<300);
  const state=await page.evaluate(()=>({action:__demo.controller.action,direction:__demo.controller.direction,x:__demo.controller.x,y:__demo.controller.y}));
  assert.equal(state.action,'walk');assert.equal(state.direction,'up_right');assert.ok(state.x>560&&state.y<300);
  await page.keyboard.up('KeyW');await page.keyboard.up('KeyD');await page.waitForFunction(()=>__demo.controller.action==='idle');
  assert.equal(await page.evaluate(()=>__demo.controller.action),'idle');
  await page.keyboard.press('KeyJ');await page.waitForFunction(()=>__demo.controller.action==='attack');assert.equal(await page.evaluate(()=>__demo.controller.action),'attack');
  await page.waitForFunction(()=>__demo.controller.action==='idle');assert.equal(await page.evaluate(()=>__demo.controller.action),'idle');
  assert.deepEqual(errors,[]);
  await page.screenshot({path:process.argv[3]||'/tmp/topdown-browser.png',fullPage:true});
  console.log('topdown preview: gallery, diagonal keyboard movement, attack and no page errors OK');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
