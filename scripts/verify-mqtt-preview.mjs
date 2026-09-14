// Runs only against the isolated MQTT QA server, never the physical controller.
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const base='http://127.0.0.1:5187';
assert.ok((await(await fetch(base+'/__qa/stats')).json()).received);
const target=await(await fetch('http://127.0.0.1:9238/json/new?'+base+'/%23iot',{method:'PUT'})).json();
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
let sequence=0;const pending=new Map(),errors=[];
ws.onmessage=event=>{const message=JSON.parse(event.data);if(message.id){const p=pending.get(message.id);pending.delete(message.id);message.error?p.reject(message.error):p.resolve(message.result)}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails.text)};
const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
async function until(expression){const end=Date.now()+20000;while(Date.now()<end){if(await evaluate(expression))return;await new Promise(resolve=>setTimeout(resolve,100))}throw Error('Timed out: '+expression)}
async function click(text,selector='button'){await until(`(()=>{const button=[...document.querySelectorAll(${JSON.stringify(selector)})].find(b=>b.innerText.trim()===${JSON.stringify(text)});return button&&!button.disabled})()`);await evaluate(`(()=>{const button=[...document.querySelectorAll(${JSON.stringify(selector)})].find(b=>b.innerText.trim()===${JSON.stringify(text)});button.click()})()`)}
async function value(selector,value,event='input'){await evaluate(`(()=>{const input=document.querySelector(${JSON.stringify(selector)});if(!input)throw Error('Missing input');input.value=${JSON.stringify(String(value))};input.dispatchEvent(new Event(${JSON.stringify(event)},{bubbles:true}))})()`)}
const stats=()=>fetch(base+'/__qa/stats').then(r=>r.json());
async function confirm(cmd,data){
 await until("!!document.querySelector('.modal-footer .primary')");
 await click('确认发送','.modal-footer button');
 await until("!document.querySelector('.modal-footer')");
 const result=await stats();const latest=result.received.at(-1);
 assert.equal(latest.topic,'tomato_hnsw0001/set');assert.equal(latest.qos,0);assert.equal(latest.retain,false);
 assert.equal(latest.payload.cmd,cmd);assert.deepEqual(latest.payload.data,data);
 await until(`(async()=>{const rows=await(await fetch('/api/commands')).json();return rows.find(row=>row.id===${JSON.stringify(latest.payload.request_id)})?.status==='acknowledged'})()`);
}
try{
 await send('Runtime.enable');await send('Page.enable');
 for(const page of await(await fetch('http://127.0.0.1:9238/json/list')).json())if(page.id!==target.id&&page.url.startsWith(base))await send('Target.closeTarget',{targetId:page.id});
 await send('Network.enable');await send('Network.clearBrowserCookies');await send('Page.navigate',{url:base+'/#iot'});
 await until("document.body.innerText.includes('协议联调（隔离测试）')&&document.body.innerText.includes('本机 MQTT 已连接并完成订阅')&&!document.querySelector('[aria-label=雾化泵]')?.disabled");
 assert.equal(await evaluate("!!document.querySelector('.mqtt-form')"),false);
 await evaluate("document.querySelector('[aria-label=雾化泵]').click()");await confirm('03',{value:1});
 await until("document.querySelector('[aria-label=雾化泵]').getAttribute('aria-checked')==='true'");
 await evaluate("document.querySelector('[aria-label=补光灯总开关]').click()");await confirm('04',{value:1});
 await evaluate("document.querySelector('.hardware-settings').open=true");
 await new Promise(resolve=>setTimeout(resolve,100));
 for(const [cmd,label,number] of [['01','红灯亮度',35],['02','蓝灯亮度',45],['05','目标补光阶段',4],['06','泵运行间隔',30],['07','泵运行时长',20]]){
  await value('[aria-label=设备设置项目]',cmd,'change');
  await value(`[aria-label="${label}"]`,number,cmd==='05'?'change':'input');
  await click('确认设置','.hardware-settings button');await confirm(cmd,{value:number});
 }
 await value('[aria-label=设备设置项目]','09','change');
 const schedule={start_hour:22,start_minute:15,end_hour:6,end_minute:45};
 for(const [label,key] of [['开始时','start_hour'],['开始分','start_minute'],['结束时','end_hour'],['结束分','end_minute']])await value(`[aria-label="${label}"]`,schedule[key]);
 await click('确认设置','.hardware-settings button');await confirm('09',schedule);
 await click('切换 AI 智控','.hardware-controls button');await confirm('08',{value:1});
 await until("document.querySelector('.hardware-controls').innerText.includes('设备 AI 智控')&&document.querySelector('[aria-label=雾化泵]').disabled");
 assert.equal(await evaluate("document.querySelector('.page-heading').innerText.includes('阈值自动模式')"),false);
 assert.equal((await stats()).state.rest_schedule.crosses_midnight,true);
 await until("document.querySelector('table').innerText.includes('泵运行时长')&&document.querySelector('table').innerText.includes('20 秒')&&document.querySelector('table').innerText.includes('22:15–06:45')");
 await evaluate("document.querySelector('.hardware-settings').open=false;document.querySelector('.mqtt-status-panel details').open=true");
 await until("!document.querySelector('.toast')");
 for(const [name,width,height] of [['desktop',1480,1050],['mobile',390,844]]){
  await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:name==='mobile'});
  await evaluate(name==='mobile'?"document.querySelector('.hardware-controls').scrollIntoView()":"window.scrollTo(0,0)");
  await new Promise(resolve=>setTimeout(resolve,300));
  const shot=await send('Page.captureScreenshot',{format:'png'});
  await writeFile(`docs/qa/mqtt-r19-${name}.png`,Buffer.from(shot.data,'base64'));
 }
 await evaluate("fetch('/api/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role:'student'})})");
 assert.equal(await evaluate("(async()=>{const r=await fetch('/api/devices/MQTT-QA/protocol-commands',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd:'08',data:{value:0},confirmed:true})});return r.status})()"),403);
 await fetch(base+'/__qa/offline',{method:'POST'});
 await until("document.querySelector('.hardware-controls').innerText.includes('等待设备实时遥测')");
 assert.equal(await evaluate("[...document.querySelectorAll('.hardware-controls button')].every(button=>button.disabled)"),true);
 const result=await stats();assert.deepEqual([...new Set(result.received.map(row=>row.payload.cmd))].sort(),['01','02','03','04','05','06','07','08','09']);
 assert.deepEqual(errors,[]);
 const report={isolated:true,all_nine_commands:true,qos:0,retained_commands:false,mode_permission_checked:true,offline_controls_disabled:true,errors,checked_at:new Date().toISOString()};
 await writeFile('docs/qa/mqtt-r19-preview.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}finally{ws.close()}
