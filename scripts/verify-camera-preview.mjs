// Browser integration checks only against the isolated camera QA containers.
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
const base='http://127.0.0.1:5186';
const cameraIP=execFileSync('docker',['inspect','--format','{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}','hydro-camera-qa-api'],{encoding:'utf8'}).trim();
const target=await(await fetch('http://127.0.0.1:9237/json/new?'+base+'/%23maturity',{method:'PUT'})).json();
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
let sequence=0;const pending=new Map(),errors=[];let unauthorized=0;
ws.onmessage=event=>{
 const message=JSON.parse(event.data);
 if(message.id){const p=pending.get(message.id);pending.delete(message.id);message.error?p.reject(message.error):p.resolve(message.result)}
 if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails.text);
 if(message.method==='Network.responseReceived'&&message.params.response.status===401)unauthorized++;
};
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value}
async function until(expression){const end=Date.now()+20000;while(Date.now()<end){if(await evaluate(expression))return;await new Promise(resolve=>setTimeout(resolve,100))}throw new Error('Timed out: '+expression)}
const api=async(path,body)=>evaluate(`(async()=>{const r=await fetch('/api'+${JSON.stringify(path)},{method:${JSON.stringify(body===undefined?'GET':'POST')},headers:{'Content-Type':'application/json'},body:${body===undefined?'undefined':JSON.stringify(JSON.stringify(body))}});if(!r.ok)throw Error(await r.text());return r.json()})()`);
async function click(text,selector='button'){await evaluate(`(()=>{const b=[...document.querySelectorAll(${JSON.stringify(selector)})].find(b=>b.innerText.trim()===${JSON.stringify(text)});if(!b||b.disabled)throw Error('Button unavailable: '+${JSON.stringify(text)});b.click()})()`)}
try{
 await send('Runtime.enable');await send('Network.enable');await send('Page.enable');
 const pages=await send('Target.getTargets');
 for(const page of pages.targetInfos)if(page.targetId!==target.id&&page.url.startsWith(base))await send('Target.closeTarget',{targetId:page.targetId});
 await send('Page.navigate',{url:base+'/#maturity'});
 await until("document.body.innerText.includes('番茄成熟度模型已就绪')");
 if(!(await api('/devices')).some(device=>device.id==='CAMERA-QA'))await api('/devices',{id:'CAMERA-QA',name:'Isolated camera check',batch:'QA',group:'QA',source:'mqtt',planted:'2026-09-14'});
 await until("document.querySelector('select[aria-label=\"选择设备\"]').value==='CAMERA-QA'");
 assert.equal(await evaluate("document.getElementById('confidence-threshold').value"),'65');
 const beforeRecords=(await api('/recognitions')).length;
 await click('拍照识别');
 await until("document.querySelector('.camera-preview video')?.videoWidth>0");
 // Closing during asynchronous canvas encoding must discard, not upload, the frame.
 await evaluate("(()=>{const original=HTMLCanvasElement.prototype.toBlob;HTMLCanvasElement.prototype.toBlob=function(...args){setTimeout(()=>original.apply(this,args),200)};[...document.querySelectorAll('.camera-modal button')].find(b=>b.innerText==='拍照并识别').click();[...document.querySelectorAll('.camera-modal button')].find(b=>b.innerText==='取消').click();HTMLCanvasElement.prototype.toBlob=original})()");
 await until("!document.querySelector('.camera-modal')");
 await new Promise(resolve=>setTimeout(resolve,400));
 assert.equal((await api('/recognitions')).length,beforeRecords);
 await click('拍照识别');
 await until("document.querySelector('.camera-preview video')?.videoWidth>0");
 // Reproduce a stale HttpOnly session immediately before taking the photo.
 await send('Network.setCookie',{name:'hydro_session',value:'expired-test-session',url:base,path:'/',httpOnly:true,sameSite:'Strict'});
 await click('拍照并识别','.camera-modal button');
 await until("!document.querySelector('.camera-modal')&&document.querySelector('.recognition-detail')");
 let records=await api('/recognitions');
 assert.equal(records.length,beforeRecords+1);assert.equal(records[0].model.confidence_threshold,0.65);
 assert.ok(unauthorized>0);
 assert.equal(await evaluate("document.querySelector('.error-banner')?.innerText||''"),'');

 await click('远程摄像头');
 await until("!!document.getElementById('remote-camera-url')");
 await evaluate(`(()=>{const input=document.getElementById('remote-camera-url');input.value='http://${cameraIP}:8091/image';input.dispatchEvent(new Event('input',{bubbles:true}))})()`);
 await click('连接摄像头','.camera-modal button');
 await until("document.querySelector('.camera-preview img')?.complete&&document.body.innerText.includes('本次获取：')");
 await until("!document.querySelector('.toast')");
 for(const [name,width,height] of [['desktop',1480,1050],['mobile',390,844]]){
  await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:name==='mobile'});
  await new Promise(resolve=>setTimeout(resolve,400));
  const screenshot=await send('Page.captureScreenshot',{format:'png'});
  await writeFile(`docs/qa/camera-${name}.png`,Buffer.from(screenshot.data,'base64'));
 }
 await click('识别这张照片','.camera-modal button');
 await until("!document.querySelector('.camera-modal')");
 records=await api('/recognitions');
 assert.equal(records.length,beforeRecords+2);
 assert.ok(records.every(record=>record.mode==='yolo'&&record.model.confidence_threshold===0.65));
 assert.deepEqual(errors,[]);
 const report={local_capture:true,session_recovered_after_401:unauthorized>0,remote_http_snapshot:true,isolated_recognition_count:records.length-beforeRecords,errors,checked_at:new Date().toISOString()};
 await writeFile('docs/qa/camera-preview.json',JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify(report));
}finally{ws.close()}
