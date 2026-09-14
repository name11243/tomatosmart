<script setup>
import {ref,nextTick,onMounted,onBeforeUnmount} from 'vue';
import {api} from './api';
const props=defineProps({initialMode:{type:String,default:'local'},busy:Boolean,submitError:String,recognize:Boolean});
const emit=defineEmits(['capture','retry','discard','close']);
const remoteUrl=defineModel('remoteUrl',{default:'http://192.168.4.1/image'});
const mode=ref(props.initialMode),video=ref(),ready=ref(false),frame=ref(null),active=ref(false),fetching=ref(false),taking=ref(false),cameraError=ref(''),captured=ref(null),preview=ref('');
let stream,timer,request,generation=0,alive=true;
function stop(){generation++;clearTimeout(timer);request?.abort();stream?.getTracks().forEach(track=>track.stop());stream=null;ready.value=false;active.value=false;fetching.value=false}
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
  frame.value=result;active.value=true;cameraError.value='';
  timer=setTimeout(()=>getFrame(turn),result.refresh_seconds*1000);
 }catch(error){
  if(!alive||turn!==generation||error.name==='AbortError')return;
  frame.value=null;active.value=false;cameraError.value=error.message;
 }finally{if(turn===generation)fetching.value=false}
}
function connect(){stop();frame.value=null;cameraError.value='';getFrame(generation)}
function disconnect(){stop();frame.value=null;cameraError.value=''}
async function switchMode(next){if(props.busy)return;stop();discard();frame.value=null;cameraError.value='';mode.value=next;await nextTick();if(next==='local')await startLocal()}
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
  <div class="camera-tabs"><button :class="{selected:mode==='local'}" :disabled="busy" @click="switchMode('local')">本机摄像头</button><button :class="{selected:mode==='remote'}" :disabled="busy" @click="switchMode('remote')">远程热点摄像头</button></div>
  <template v-if="mode==='remote'&&!captured">
   <p class="camera-help">ESP32-P4 摄像头：让运行本系统的电脑连接设备热点或同一局域网，再填写设备 IP。固件约每 20 秒更新一张照片；设备须同时连上 Wi-Fi 网络且 USB 摄像头就绪，才会自动采集。</p>
   <label for="remote-camera-url">摄像头地址</label>
   <div class="camera-connect"><input id="remote-camera-url" v-model="remoteUrl" placeholder="http://192.168.4.1/image" :disabled="active||fetching||busy" @keydown.enter.prevent="connect"/><button class="primary" :disabled="fetching||busy" @click="active?disconnect():connect()">{{fetching?'连接中…':active?'断开':'连接摄像头'}}</button></div>
  </template>
  <div class="camera-preview">
   <img v-if="captured" :src="preview" alt="已保留的待保存照片"/>
   <video v-else-if="mode==='local'" ref="video" autoplay muted playsinline @loadeddata="ready=true" @emptied="ready=false"/>
   <img v-else-if="frame" :src="frame.image" alt="远程设备最新照片"/>
   <p v-else>{{fetching?'正在获取设备照片…':'连接后显示设备最新照片'}}</p>
  </div>
  <p v-if="mode==='remote'&&frame&&!captured" class="camera-help">本次获取：{{new Date(frame.fetched_at).toLocaleTimeString('zh-CN')}} · 固件未提供实际采集时间。<button class="text-button" :disabled="fetching||busy" @click="connect">立即刷新</button></p>
  <p v-if="captured" class="camera-help">{{busy?'正在保存照片…':'照片已暂存，登录失效或上传失败时可继续重试。'}}</p>
  <div v-if="cameraError||submitError" class="error-inline" role="alert">{{cameraError||submitError}}</div>
  <div class="actions camera-actions"><button :disabled="busy" @click="emit('close')">取消</button><template v-if="captured"><button :disabled="busy" @click="retake">重新拍摄</button><button class="primary" :disabled="busy" @click="emit('retry')">{{busy?'保存中…':'重试保存'}}</button></template><button v-else class="primary" :disabled="busy||(mode==='local'?!ready:!active||!frame)" @click="capture">{{mode==='remote'?(recognize?'识别这张照片':'保存这张照片'):(recognize?'拍照并识别':'拍照保存')}}</button></div>
 </section></div>
</template>

<style scoped>
.camera-modal{width:min(680px,95vw)}.camera-tabs{display:flex;gap:10px;margin:16px 0}.camera-tabs button{flex:1}.camera-tabs .selected{background:#e8f3e9;border-color:#327459;color:#20543f}.camera-help{font-size:12px;margin:10px 0;line-height:1.7}.camera-connect{display:flex;gap:10px;margin:8px 0 16px}.camera-connect input{flex:1;min-width:0}.camera-preview{background:#edf1ed;border-radius:5px;min-height:180px;display:flex;align-items:center;justify-content:center;overflow:hidden;margin:12px 0}.camera-preview video,.camera-preview img{display:block;width:100%;max-height:360px;object-fit:contain}.camera-preview p{padding:32px 16px;font-size:13px}.camera-actions{justify-content:flex-end;margin-top:16px;flex-wrap:wrap}@media(max-width:640px){.camera-modal{padding:18px}.camera-tabs{gap:6px}.camera-tabs button{font-size:12px;padding:9px 6px}.camera-connect{flex-wrap:wrap}.camera-connect input{flex-basis:100%}.camera-connect button{width:100%}.camera-preview video,.camera-preview img{max-height:260px}.camera-actions button{font-size:12px;padding:8px 10px}}
</style>
