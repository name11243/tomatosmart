import assert from 'node:assert/strict';
import {mkdir, writeFile} from 'node:fs/promises';

// Uses an isolated Edge profile started with --remote-debugging-port=9236.
const target = await (await fetch('http://127.0.0.1:9236/json/new?http://127.0.0.1:5176/%23maturity', {method:'PUT'})).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
let sequence=0;
const pending=new Map(),errors=[];
ws.onmessage=e=>{
 const message=JSON.parse(e.data);
 if(message.id){const p=pending.get(message.id);pending.delete(message.id);message.error?p.reject(message.error):p.resolve(message.result)}
 if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails.text);
};
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value}
try{
 await send('Runtime.enable');
 await send('Page.enable');
 await send('Page.navigate',{url:'http://127.0.0.1:5176/#maturity'});
 const deadline=Date.now()+30000;
 while(Date.now()<deadline){if(await evaluate("document.body.innerText.includes('番茄成熟度模型已就绪')"))break;await new Promise(resolve=>setTimeout(resolve,500))}
 const result=await evaluate(`(async()=>({text:document.body.innerText,error:document.querySelector('.error-banner')?.innerText||'',buttons:[...document.querySelectorAll('.page-heading button')].map(b=>({text:b.innerText,disabled:b.disabled})),health:await (await fetch('/api/health')).json()}))()`);
 assert.equal(result.health.real_only,true);
 assert.equal(result.health.model.ready,true);
 assert.ok(result.text.includes('番茄成熟度模型已就绪'));
 assert.equal(result.error,'');
 assert.deepEqual(errors,[]);
 assert.equal(await evaluate("document.getElementById('confidence-threshold').value"),'65');
 const stored=await evaluate("(async()=>await (await fetch('/api/recognitions')).json())()");
 const filterChecks=[];
 if(stored.length){
  const record=stored[0];
  for(const threshold of [65,90,95,10]){
   await evaluate(`(()=>{const slider=document.getElementById('confidence-threshold');slider.value=${threshold};slider.dispatchEvent(new Event('input',{bubbles:true}))})()`);
   const expected=record.detections.filter(d=>d.confidence>=threshold/100).length;
   const imageDeadline=Date.now()+10000;
   while(Date.now()<imageDeadline){if(await evaluate("!!document.querySelector('.recognition-image svg')"))break;await new Promise(resolve=>setTimeout(resolve,100))}
   await new Promise(resolve=>setTimeout(resolve,100));
   const actual=await evaluate("({rows:document.querySelectorAll('.recognition-detail tbody tr').length,boxes:document.querySelectorAll('.recognition-image .detection-box').length,count:parseInt(document.querySelector('.recognition-detail .summary-strip strong').innerText),source:document.querySelector('.recognition-image img').getAttribute('src'),scores:[...document.querySelectorAll('.detection-box')].map(b=>Number(b.dataset.confidence))})");
   assert.equal(actual.rows,expected);
   assert.equal(actual.boxes,expected);
   assert.equal(actual.count,expected);
   assert.equal(actual.source,record.original);
   assert.ok(actual.scores.every(score=>score>=threshold/100));
   filterChecks.push({threshold,expected,actual:actual.count});
  }
  await evaluate("[...document.querySelectorAll('.confidence-setting button')].find(b=>b.innerText.includes('恢复默认')).click()");
  await new Promise(resolve=>setTimeout(resolve,100));
  assert.equal(await evaluate("document.getElementById('confidence-threshold').value"),'65');
  assert.deepEqual(await evaluate("(async()=>await (await fetch('/api/recognitions')).json())()"),stored);
 }
 await mkdir('docs/qa',{recursive:true});
 for(const [name,width,height] of [['desktop',1480,1050],['mobile',390,844]]){
  await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:name==='mobile'});
  await new Promise(resolve=>setTimeout(resolve,700));
  const screenshot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
  await writeFile(`docs/qa/vision-${name}.png`,Buffer.from(screenshot.data,'base64'));
 }
 await writeFile('docs/qa/vision-preview.json',JSON.stringify({...result,filterChecks,errors,checked_at:new Date().toISOString()},null,2)+'\n');
 console.log(JSON.stringify({model:result.health.model,buttons:result.buttons,filterChecks,errors}));
}finally{ws.close()}
