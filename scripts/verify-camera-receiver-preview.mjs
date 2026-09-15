// Verify actual ESP32 uploads and browser refresh; never upload fixtures to live data.
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const base='http://127.0.0.1:5176';
const target=await(await fetch('http://127.0.0.1:9237/json/new?about:blank',{method:'PUT'})).json();
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
let sequence=0;const pending=new Map(),errors=[];
ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails)};
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
async function until(expression,timeout=30000){const end=Date.now()+timeout;while(Date.now()<end){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,250))}throw Error('Timed out: '+expression)}
async function click(text){await evaluate(`(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.innerText.trim()===${JSON.stringify(text)});if(!b||b.disabled)throw Error('Button unavailable');b.click()})()`)}
async function screenshot(name,width,height){await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<600});await new Promise(r=>setTimeout(r,400));assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'));const shot=await send('Page.captureScreenshot',{format:'png'});await writeFile('docs/qa/'+name+'.png',Buffer.from(shot.data,'base64'))}
try{
 await send('Runtime.enable');await send('Page.enable');
 // This port belongs to the dedicated Codex QA profile. Close old QA tabs and polling.
 const pages=await send('Target.getTargets');for(const p of pages.targetInfos)if(p.type==='page'&&p.targetId!==target.id&&p.url.startsWith(base))await send('Target.closeTarget',{targetId:p.targetId});
 await send('Emulation.setDeviceMetricsOverride',{width:1480,height:1080,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:base+'/#maturity'});
 await until("[...document.querySelectorAll('button')].some(b=>b.innerText.trim()==='远程摄像头'&&!b.disabled)");
 await evaluate("(()=>{window.__cameraFrames=[];const original=window.fetch;window.fetch=async(...args)=>{const r=await original(...args);if(String(args[0]).endsWith('/api/camera/frame')){const v=await r.clone().json();window.__cameraFrames.push({received_at:v.received_at,receiver_waiting:v.receiver_waiting,source_url:v.source_url,captured_at:v.captured_at,stale:v.stale,has_image:!!v.image})}return r}})()");
 await click('远程摄像头');await until("!!document.getElementById('remote-camera-url')");
 assert.equal(await evaluate("document.getElementById('remote-camera-url').value"),'http://192.168.31.217:500/snapshot');
 await click('连接摄像头');await until("document.querySelector('.camera-preview img')?.naturalWidth>0");
 assert.equal(await evaluate("document.querySelector('.camera-modal .error-inline')?.innerText||''"),'');
 await screenshot('camera-receiver-desktop',1480,1080);
 await screenshot('camera-receiver-mobile',390,844);
 await until('window.__cameraFrames.length>=2',30000);
 const frames=await evaluate('window.__cameraFrames');
 assert.ok(frames.every(f=>f.has_image&&!f.receiver_waiting&&f.captured_at===null));
 assert.ok(frames.at(-1).received_at>frames[0].received_at,'New ESP32 push must be reflected by auto refresh');
 const receiver=await evaluate("fetch('/api/camera/receiver').then(r=>r.json())");
 assert.ok(receiver.has_photo&&!receiver.stale);assert.equal(receiver.source,'http_upload');
 assert.deepEqual(errors,[]);
 const result={checked_at:new Date().toISOString(),receiver,frames,browser_errors:errors,auto_refresh_verified:true};
 await writeFile('docs/qa/camera-receiver-check.json',JSON.stringify(result,null,2));
 console.log(JSON.stringify(result,null,2));
}finally{ws.close()}
