let recoverSession=null,recovery=null;
export function setSessionRecovery(handler){recoverSession=handler}
export async function api(path, body, method, extra={}) {
 const options={...extra,method:method || (body===undefined?'GET':'POST'),credentials:'same-origin'};
 if(body instanceof FormData) options.body=body;
 else if(body!==undefined){options.headers={'Content-Type':'application/json'}; options.body=JSON.stringify(body)}
 let r=await fetch('/api'+path,options);
 // Authentication rejects these requests before their handlers run; retry once.
 if(r.status===401&&path!=='/session'&&recoverSession){
  if(!recovery)recovery=Promise.resolve().then(recoverSession).catch(()=>false).finally(()=>{recovery=null});
  if(await recovery)r=await fetch('/api'+path,options);
 }
 if(!r.ok){let data;try{data=await r.json()}catch{};const error=new Error(typeof data?.detail==='string'?data.detail:Array.isArray(data?.detail)?data.detail.map(x=>x.msg).join('；'):'服务暂不可用');error.status=r.status;throw error}
 return r.json();
}
export const download=(kind,format,device='')=>window.open(`/api/export/${kind}?format=${format}&device=${encodeURIComponent(device)}`,'_blank');
