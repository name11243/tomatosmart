import {test,afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {api,setSessionRecovery} from '../src/api.js';
const originalFetch=globalThis.fetch;
afterEach(()=>{globalThis.fetch=originalFetch;setSessionRecovery(null)});
const response=(status,value)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});

test('replays rejected photo FormData once after session recovery',async()=>{
 const form=new FormData();form.append('file',new Blob(['test-only-photo']),'camera.jpg');
 const bodies=[];let loggedIn=false,recovered=0;
 globalThis.fetch=async(url,options)=>{bodies.push(options.body);return loggedIn?response(200,{id:'photo'}):response(401,{detail:'expired'})};
 setSessionRecovery(async()=>{recovered++;loggedIn=true;return true});
 assert.deepEqual(await api('/photos',form),{id:'photo'});
 assert.equal(recovered,1);assert.deepEqual(bodies,[form,form]);
});

test('concurrent unauthorized requests share session recovery',async()=>{
 let loggedIn=false,recovered=0;
 globalThis.fetch=async()=>loggedIn?response(200,{ok:true}):response(401,{detail:'expired'});
 setSessionRecovery(async()=>{recovered++;await new Promise(resolve=>setTimeout(resolve,20));loggedIn=true;return true});
 await Promise.all([api('/devices'),api('/alerts'),api('/commands')]);
 assert.equal(recovered,1);
});

test('password login requirement leaves the photo request rejected',async()=>{
 let requests=0;globalThis.fetch=async()=>{requests++;return response(401,{detail:'login required'})};
 setSessionRecovery(async()=>false);
 await assert.rejects(api('/photos',new FormData()),error=>error.status===401);
 assert.equal(requests,1);
});

test('does not replay forbidden, failed, or still-unauthenticated requests',async()=>{
 for(const status of [403,500,401]){
  let requests=0,recovered=0;
  globalThis.fetch=async()=>{requests++;return response(status,{detail:'rejected'})};
  setSessionRecovery(async()=>{recovered++;return true});
  await assert.rejects(api('/photos',new FormData()),error=>error.status===status);
  assert.equal(requests,status===401?2:1);assert.equal(recovered,status===401?1:0);
 }
});

test('incorrect login credentials never trigger automatic recovery',async()=>{
 let recovered=0;globalThis.fetch=async()=>response(401,{detail:'bad password'});
 setSessionRecovery(async()=>{recovered++;return true});
 await assert.rejects(api('/session',{role:'teacher',password:'wrong'}),error=>error.status===401);
 assert.equal(recovered,0);
});
