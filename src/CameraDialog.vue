<script setup>
import {ref,computed,watch,nextTick,onMounted,onBeforeUnmount} from 'vue';
import {api} from './api';
const props=defineProps({initialMode:{type:String,default:'local'},busy:Boolean,submitError:String,recognize:Boolean,savedUrl:{type:String,default:''}});
const emit=defineEmits(['capture','retry','discard','close','save-address']);
const remoteUrl=defineModel('remoteUrl',{default:''});
// The backend YAML is the only authority for the default address; nothing is hard-coded here.
const defaultAddress=computed(()=>props.savedUrl||'未在后端配置');
const addressChanged=computed(()=>!!remoteUrl.value.trim()&&remoteUrl.value.trim()!==(props.savedUrl||'').trim());
const mode=ref(props.initialMode),video=ref(),ready=ref(false),frame=ref(null),active=ref(false),fetching=ref(false),taking=ref(false),cameraError=ref(''),captured=ref(null),preview=ref(''),probing=ref(false),report=ref(null);
const waitingUpload=ref(false);
let stream,timer,request,generation=0,alive=true;
function stop(){generation++;clearTimeout(timer);request?.abort();stream?.getTracks().forEach(track=>track.stop());stream=null;ready.value=false;active.value=false;fetching.value=false;probing.value=false;waitingUpload.value=false}
function schedule(turn,seconds){clearTimeout(timer);timer=setTimeout(()=>getFrame(turn),Math.max(5,Number(seconds)||20)*1000)}
function discard(){if(preview.value)URL.revokeObjectURL(preview.value);preview.value='';captured.value=null;emit('discard')}
async function startLocal(){
 stop();cameraError.value='';const turn=generation;
 if(!navigator.mediaDevices?.getUserMedia){cameraError.value='当前浏览器未开放相机权限，请使用本机 localhost/HTTPS 页面，或上传照片。';return}
 try{
  const media=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'},audio:false});
  if(!alive||turn!==generation){media.getTracks().forEach(track=>track.stop());return}
  stream=media;await nextTick();if(video.value)video.value.srcObject=stream;
 }catch{if(turn===generation)cameraError.value='无法开启本机相机，请检查浏览器相机权限及设备占用。'}
}
async function getFrame(turn){
 if(!alive||turn!==generation||captured.value)return;
 fetching.value=true;request=new AbortController();
 try{
  const result=await api('/camera/frame',{url:remoteUrl.value},'POST',{signal:request.signal});
  if(!alive||turn!==generation)return;
  waitingUpload.value=!!result.receiver_waiting;frame.value=result.image?result:null;active.value=true;cameraError.value='';report.value=null;
  schedule(turn,result.refresh_seconds);
 }catch(error){
  if(!alive||turn!==generation||error.name==='AbortError')return;
  frame.value=null;active.value=false;waitingUpload.value=false;cameraError.value=error.message;
 }finally{if(turn===generation)fetching.value=false}
}
function connect(){stop();frame.value=null;cameraError.value='';report.value=null;getFrame(generation)}
function disconnect(){stop();frame.value=null;cameraError.value=''}
// Ask the backend to try the address and the known photo endpoints, and show every attempt.
async function diagnose(){
 if(probing.value||props.busy||!remoteUrl.value.trim())return;
 stop();frame.value=null;cameraError.value='';report.value=null;probing.value=true;
 const turn=generation;request=new AbortController();
 try{
  const result=await api('/camera/probe',{url:remoteUrl.value},'POST',{signal:request.signal});
  if(!alive||turn!==generation)return;
  report.value=result;
  if(result.ok||result.receiver_waiting){
   waitingUpload.value=!!result.receiver_waiting;frame.value=result.image?result:null;
   active.value=true;schedule(turn,result.refresh_seconds);
  }else{cameraError.value=result.message}
 }catch(error){if(alive&&turn===generation)cameraError.value=error.message}
 finally{if(turn===generation)probing.value=false}
}
function useDetected(){if(report.value?.source_url)remoteUrl.value=report.value.source_url}
// Editing an address invalidates the old preview and any in-flight response.
// The next explicit connection always uses the latest input value.
watch(remoteUrl,()=>{if(mode.value==='remote'&&!captured.value){stop();frame.value=null;report.value=null;cameraError.value=''}},{flush:'sync'});
async function switchMode(next){if(props.busy)return;stop();discard();frame.value=null;cameraError.value='';report.value=null;mode.value=next;await nextTick();if(next==='local')await startLocal()}
async function capture(){
 if(props.busy||taking.value||captured.value)return;
 taking.value=true;
 const turn=generation;
 cameraError.value='';
 try{
  let blob;
  if(mode.value==='remote'){
   if(!active.value||!frame.value)return;
   blob=await (await fetch(frame.value.image)).blob();
  }else{
   if(!ready.value||!video.value?.videoWidth){cameraError.value='相机画面尚未就绪，请稍后拍照。';return}
   const canvas=document.createElement('canvas');canvas.width=video.value.videoWidth;canvas.height=video.value.videoHeight;
   canvas.getContext('2d').drawImage(video.value,0,0);
   blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',0.92));
  }
  if(!alive||turn!==generation)return;
  if(!blob)throw new Error('拍照失败，请重试。');
  const file=new File([blob],mode.value==='remote'?'remote-camera.jpg':'camera.jpg',{type:'image/jpeg'});
  captured.value=file;preview.value=URL.createObjectURL(blob);stop();
  emit('capture',{file,captureSource:mode.value==='remote'?'remote_camera':'local_camera'});
 }catch(error){cameraError.value=error.message}finally{taking.value=false}
}
async function retake(){discard();if(mode.value==='local')await startLocal();else connect()}
onMounted(()=>{if(mode.value==='local')startLocal()});
onBeforeUnmount(()=>{alive=false;stop();if(preview.value)URL.revokeObjectURL(preview.value)});
</script>

<template>
 <div class="overlay modal-overlay"><section class="modal camera-modal" role="dialog" aria-modal="true" aria-labelledby="camera-heading">
  <div class="drawer-heading"><h2 id="camera-heading">{{recognize?'采集番茄照片':'拍照留存'}}</h2><button aria-label="关闭相机" :disabled="busy" @click="emit('close')"><i class="ri-close-line"/></button></div>
  <div class="camera-tabs"><button :class="{selected:mode==='local'}" :disabled="busy" @click="switchMode('local')">本机摄像头</button><button :class="{selected:mode==='remote'}" :disabled="busy" @click="switchMode('remote')">远程摄像头</button></div>
  <template v-if="mode==='remote'&&!captured">
   <p class="camera-help">默认地址：{{defaultAddress}}。支持修改 IP、端口及照片路径，点击连接后使用输入的新地址。</p>
   <label for="remote-camera-url">摄像头地址</label>
   <div class="camera-connect"><input id="remote-camera-url" v-model="remoteUrl" :placeholder="savedUrl||'http://设备IP:端口/snapshot'" :disabled="busy" @keydown.enter.prevent="connect"/><button class="primary" :disabled="fetching||probing||busy||!remoteUrl.trim()" @click="active?disconnect():connect()">{{fetching?'连接中…':active?'断开':'连接摄像头'}}</button></div>
   <div class="camera-connect"><button :disabled="probing||busy||!remoteUrl.trim()" @click="diagnose">{{probing?'检测中…':'检测连接'}}</button><span class="camera-help">检测会从后端（Docker 容器内）依次请求该地址与 /snapshot、/image、/download，并说明每个地址的结果。</span></div>
   <p class="camera-help">修改地址后点击“连接摄像头”即请求新地址。<button class="text-button" :disabled="busy||!remoteUrl.trim()||!addressChanged" @click="emit('save-address',remoteUrl.trim())">{{addressChanged?'保存为默认地址':'当前已是默认地址'}}</button>保存后写入后端配置，其他账号与刷新页面同样生效。</p>
  </template>
  <div v-if="mode==='remote'&&report" class="camera-report">
   <p><strong>{{report.receiver_waiting?'服务已连通，等待上传':report.ok?'检测成功':'检测失败'}}</strong> · 目标地址 {{report.requested_url}}</p>
   <ul><li v-for="item in report.attempts" :key="item.url"><code>{{item.url}}</code><span>{{item.message}}<template v-if="item.status">（HTTP {{item.status}}，{{item.elapsed_ms}} ms）</template></span></li></ul>
   <p v-if="report.endpoint_detected">设备实际照片接口是 <code>{{report.source_url}}</code>。<button class="text-button" @click="useDetected">改用该地址</button></p>
   <ul v-if="!report.ok&&!report.receiver_waiting&&report.advice?.length" class="camera-advice"><li v-for="line in report.advice" :key="line">{{line}}</li></ul>
  </div>
  <div class="camera-preview">
   <img v-if="captured" :src="preview" alt="已保留的待保存照片"/>
   <video v-else-if="mode==='local'" ref="video" autoplay muted playsinline @loadeddata="ready=true" @emptied="ready=false"/>
   <img v-else-if="frame" :src="frame.image" alt="远程设备最新照片"/>
   <p v-else>{{fetching?'正在获取设备照片…':probing?'正在检测摄像头地址…':waitingUpload?'接收服务已连通，等待 ESP32-P4 上传照片；收到后自动显示。':'连接后显示设备最新照片'}}</p>
  </div>
  <p v-if="mode==='remote'&&frame&&!captured" class="camera-help">实际照片地址：{{frame.source_url}}<br/>本次获取：{{new Date(frame.fetched_at).toLocaleTimeString('zh-CN')}} · 摄像头未提供实际采集时间，这里只记录获取时间。<button class="text-button" :disabled="fetching||busy" @click="connect">立即刷新</button></p>
  <p v-if="mode==='remote'&&frame?.received_at&&!captured" :class="frame.stale?'camera-warn':'camera-help'">服务接收于：{{new Date(frame.received_at).toLocaleString('zh-CN')}}{{frame.stale?' · 超过 60 秒未收到新推送，当前显示最后一张照片。':' · 这是服务器接收时间，实际采集时间未知。'}}</p>
  <p v-if="captured" class="camera-help">{{busy?'正在保存照片…':'照片已暂存，登录失效或上传失败时可继续重试。'}}</p>
  <div v-if="cameraError||submitError" class="error-inline" role="alert">{{cameraError||submitError}}</div>
  <div class="actions camera-actions"><button :disabled="busy" @click="emit('close')">取消</button><template v-if="captured"><button :disabled="busy" @click="retake">重新拍摄</button><button class="primary" :disabled="busy" @click="emit('retry')">{{busy?'保存中…':'重试保存'}}</button></template><button v-else class="primary" :disabled="busy||(mode==='local'?!ready:!active||!frame)" @click="capture">{{mode==='remote'?(recognize?'识别这张照片':'保存这张照片'):(recognize?'拍照并识别':'拍照保存')}}</button></div>
 </section></div>
</template>

<style scoped>
.camera-modal{width:min(680px,95vw)}.camera-tabs{display:flex;gap:10px;margin:16px 0}.camera-tabs button{flex:1}.camera-tabs .selected{background:#e8f3e9;border-color:#327459;color:#20543f}.camera-help{font-size:12px;margin:10px 0;line-height:1.7}.camera-connect{display:flex;gap:10px;margin:8px 0;align-items:center}.camera-connect input{flex:1;min-width:0}.camera-connect .camera-help{flex:1}.camera-warn{font-size:12px;line-height:1.7;margin:10px 0;padding:9px 11px;border-radius:4px;color:#8a5a1c;background:#fdf3e0}.camera-report{border:1px solid #e2e6e2;border-radius:5px;padding:10px 12px;margin:8px 0;font-size:12px}.camera-report p{margin:4px 0;font-size:12px}.camera-report ul{margin:6px 0;padding-left:18px}.camera-report li{margin:3px 0;line-height:1.6;color:#5f6b70}.camera-report code{color:#28694f;word-break:break-all}.camera-report span{margin-left:6px}.camera-advice li{color:#8a5a1c}.camera-preview{background:#edf1ed;border-radius:5px;min-height:180px;display:flex;align-items:center;justify-content:center;overflow:hidden;margin:12px 0}.camera-preview video,.camera-preview img{display:block;width:100%;max-height:360px;object-fit:contain}.camera-preview p{padding:32px 16px;font-size:13px}.error-inline{white-space:pre-line}.camera-actions{justify-content:flex-end;margin-top:16px;flex-wrap:wrap}@media(max-width:640px){.camera-modal{padding:18px}.camera-tabs{gap:6px}.camera-tabs button{font-size:12px;padding:9px 6px}.camera-connect{flex-wrap:wrap}.camera-connect input{flex-basis:100%}.camera-connect button{width:100%}.camera-connect .camera-help{flex-basis:100%}.camera-preview video,.camera-preview img{max-height:260px}.camera-actions button{font-size:12px;padding:8px 10px}}
</style>
