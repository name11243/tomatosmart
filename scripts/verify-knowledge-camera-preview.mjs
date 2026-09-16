// Read-only browser checks against actual local services. No device commands or test photos.
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const base='http://127.0.0.1:5176';
const target=await(await fetch('http://127.0.0.1:9237/json/new?about:blank',{method:'PUT'})).json();
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
let sequence=0;const pending=new Map(),errors=[],cameraRequests=[];
ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}
 if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);
 if(m.method==='Network.requestWillBeSent'&&m.params.request.url.endsWith('/api/camera/frame'))cameraRequests.push(JSON.parse(m.params.request.postData));};
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
async function until(expression,timeout=20000){const end=Date.now()+timeout;while(Date.now()<end){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,200))}throw Error('Timed out: '+expression)}
async function click(text,selector='button'){await evaluate(`(()=>{const b=[...document.querySelectorAll(${JSON.stringify(selector)})].find(b=>b.innerText.trim()===${JSON.stringify(text)});if(!b||b.disabled)throw Error('Button unavailable: '+${JSON.stringify(text)});b.click()})()`)}
async function input(selector,value){await evaluate(`(()=>{const i=document.querySelector(${JSON.stringify(selector)});if(!i||i.disabled)throw Error('Input unavailable');i.value=${JSON.stringify(value)};i.dispatchEvent(new Event('input',{bubbles:true}))})()`)}
async function screenshot(name,width,height){await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<600});await new Promise(r=>setTimeout(r,400));assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Horizontal overflow: '+name);const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile('docs/qa/'+name+'.png',Buffer.from(shot.data,'base64'))}
const result={};
try{
 await send('Runtime.enable');await send('Network.enable');await send('Page.enable');
 await send('Emulation.setDeviceMetricsOverride',{width:1480,height:1080,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:base+'/#maturity'});
 await until("document.body?.innerText.includes('番茄成熟度模型已就绪')");
 await until("[...document.querySelectorAll('button')].some(b=>b.innerText.trim()==='远程摄像头'&&!b.disabled)");
 await click('远程摄像头');await until("!!document.getElementById('remote-camera-url')");
 result.defaultAddress=await evaluate("document.getElementById('remote-camera-url').value");
 assert.equal(result.defaultAddress,'http://192.168.31.217:500/snapshot');
 await click('连接摄像头','.camera-modal button');
 await until("!!document.querySelector('.camera-modal .error-inline')||!!document.querySelector('.camera-preview img')");
 result.cameraError=await evaluate("document.querySelector('.camera-modal .error-inline')?.innerText||''");
 assert.equal(cameraRequests[0].url,result.defaultAddress);
 await screenshot('camera-address-desktop',1480,1080);
 await screenshot('camera-address-mobile',390,844);
 await input('#remote-camera-url','http://172.24.16.1:500/snapshot');
 await click('连接摄像头','.camera-modal button');await until("!!document.querySelector('.camera-modal .error-inline')||!!document.querySelector('.camera-preview img')");
 assert.equal(cameraRequests.at(-1).url,'http://172.24.16.1:500/snapshot');result.changedAddressRequested=true;
 await input('#remote-camera-url',result.defaultAddress);await click('取消','.camera-modal button');
 await send('Emulation.setDeviceMetricsOverride',{width:1480,height:1080,deviceScaleFactor:1,mobile:false});
 await evaluate("location.hash='knowledge'");
 await until("document.body?.innerText.includes('Python 图谱已就绪')");
 result.graphNodes=await evaluate("document.querySelector('.graph-canvas')?.getAttribute('_echarts_instance_')!=null");assert.ok(result.graphNodes);
 await screenshot('knowledge-overview-desktop',1480,1080);
 await evaluate("(()=>{const original=window.fetch;window.fetch=async(...args)=>{const r=await original(...args);if(String(args[0]).endsWith('/api/ask'))window.__qaAnswer=await r.clone().json();return r}})()");
 await input('input[aria-label="输入种植问题"]','MQTT 使用哪些主题？');await click('查询');
 await until('!!window.__qaAnswer',210000);
 result.answer=await evaluate('window.__qaAnswer');assert.equal(result.answer.mode,'local_ai',JSON.stringify(result.answer));
 assert.ok(result.answer.generation.statements.length);assert.ok(result.answer.items.every(k=>k.verified===false));
 await screenshot('knowledge-ai-desktop',1480,1080);await screenshot('knowledge-ai-mobile',390,844);
 await click('知识库浏览');await until("document.body?.innerText.includes('MQTT 主题与消息方向')");
 await click('编辑');await until("!!document.querySelector('.knowledge-fields')");
 await screenshot('knowledge-editor-mobile',390,844);await click('取消','.knowledge-dialog button');
 for(const route of ['overview','iot','maturity','archives','logs','growth','courses','devices','profile']){
  await evaluate('location.hash='+JSON.stringify(route));await new Promise(r=>setTimeout(r,800));
  assert.equal(await evaluate("document.querySelector('.error-banner')?.innerText||''"),'','Route error: '+route);
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Route overflow: '+route);
 }
 assert.deepEqual(errors,[]);result.errors=errors;result.checkedAt=new Date().toISOString();
 await writeFile('docs/qa/knowledge-camera-check.json',JSON.stringify(result,null,2));
 console.log(JSON.stringify({defaultAddress:result.defaultAddress,cameraError:result.cameraError,changedAddressRequested:result.changedAddressRequested,model:result.answer.generation.model,elapsed:result.answer.generation.elapsed_seconds,sources:result.answer.items.length,errors},null,2));
}finally{ws.close()}
