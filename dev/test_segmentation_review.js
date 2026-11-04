// Local Chromium test. No server, network, engine, or image upload.
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require('playwright');
(async()=>{
 const dir=path.resolve(process.argv[2]);
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||'/usr/bin/chromium'});
 try{
 const page=await browser.newPage({viewport:{width:1250,height:1050}});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>route.request().url()==='http://localhost/review.html'?route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(dir,'review.html'))}):route.abort());
 await page.goto('http://localhost/review.html');await page.waitForFunction(()=>window.layersReady);
 const count=await page.locator('input[type=checkbox]').count();assert(count>0);
 const pixels=()=>page.evaluate(()=>{const a=document.querySelector('canvas').getContext('2d').getImageData(0,0,c.width,c.height).data;let count=0;for(let i=3;i<a.length;i+=4)if(a[i])count++;return count});
 const report=JSON.parse(fs.readFileSync(path.join(dir,'review.json')));assert.equal(await pixels(),report.proof.selected_pixels);
 const png=await page.evaluate(()=>document.querySelector('canvas').toDataURL('image/png').split(',')[1]);fs.writeFileSync(path.join(dir,'browser-composite.png'),Buffer.from(png,'base64'));
 await page.screenshot({path:path.join(dir,'browser-review.png'),fullPage:true});
 for(let i=0;i<2;i++){await page.click('#none');assert.equal(await pixels(),0);await page.click('#all');assert.equal(await pixels(),report.proof.selected_pixels)}
 for(let i=0;i<count;i++){await page.locator('#list label').nth(i).getByRole('button',{name:'Isolate',exact:true}).click();assert.equal(await pixels(),report.layers[i].pixels);assert.equal(await page.locator('input:checked').count(),1)}
 await page.selectOption('#mode','source');assert.equal(await pixels(),report.canvas[0]*report.canvas[1]);
 await page.selectOption('#mode','overlay');assert.equal(await pixels(),report.canvas[0]*report.canvas[1]);
 await page.selectOption('#mode','composite');await page.click('#all');assert.equal(await pixels(),report.proof.selected_pixels);
 const row=page.locator('#list label').first();
 await row.locator('select').selectOption('anatomy');await row.locator('input:not([type=checkbox])').fill('visible fragment');await row.getByRole('button',{name:'Assign',exact:true}).click();
 assert.equal(await page.evaluate(()=>window.ownershipReview.assignments[0].name),'visible fragment');
 await row.getByRole('button',{name:'Claim overlapping pixels',exact:true}).click();assert.deepEqual(await page.evaluate(()=>window.ownershipReview.claims),[0]);
 await page.click('#undo');assert.deepEqual(await page.evaluate(()=>window.ownershipReview.claims),[]);
 await page.click('#reset');assert.equal(await page.evaluate(()=>window.ownershipReview.assignments[0]),null);
 await page.click('#undo');assert.equal(await page.evaluate(()=>window.ownershipReview.assignments[0].name),'visible fragment');
 await page.selectOption('#mode','ownership');assert.equal(await page.evaluate(()=>window.ownershipReview.export().binding_gate.allowed),false);
 await page.setViewportSize({width:390,height:844});assert(await page.locator('canvas').isVisible());
 assert.deepEqual(errors,[]);console.log(`PASS: ${count} isolated masks, composite/all/hide/repeated clicks, source/overlay modes, mobile visibility, no page errors`);
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
