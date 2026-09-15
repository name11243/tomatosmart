<script setup>
import {reactive,ref} from 'vue';
import {api} from './api';

const props=defineProps({mqtt:{type:Object,required:true}});
const emit=defineEmits(['close','changed']);
const form=reactive({});
const busy=ref(false),error=ref(''),message=ref(''),showPassword=ref(false);
const defaults={protocol:'tomato_v1_1',host:'',port:1883,client_id:'',username:'',password:'',tls:false,qos:0,keepalive:120,device_id:'HY-001',autoconnect:true,telemetry_topic:'',command_topic:'',ack_topic:'',state_topic:'',availability_topic:''};

function load(){Object.assign(form,defaults,props.mqtt.config||{},{password:''})}
// The parent refreshes MQTT status every two seconds. Initialize the draft once
// so a status refresh never overwrites text while somebody is editing it.
load();

async function perform(fn){
 if(busy.value)return;
 busy.value=true;error.value='';message.value='';
 try{await fn()}catch(e){error.value=e.message}finally{busy.value=false}
}
async function save(){
 await perform(async()=>{
  const payload={...form};delete payload.password_set;
  await api('/mqtt',payload,'PUT');
  message.value='配置已保存，旧连接已断开。';form.password='';
  emit('changed');
 });
}
async function action(name){
 await perform(async()=>{
  const result=await api('/mqtt/'+name,{},'POST');
  message.value=result.message;
  emit('changed');
 });
}
</script>

<template>
 <div class="overlay mqtt-drawer-overlay" @click.self="$emit('close')">
  <aside class="drawer mqtt-config-drawer" role="dialog" aria-label="MQTT 完整配置">
   <div class="drawer-heading">
    <div><span class="eyebrow">连接设置</span><h2>MQTT 完整配置</h2><p>连接参数保存到后端 YAML，修改后需重新连接。</p></div>
    <button type="button" aria-label="关闭 MQTT 配置" @click="$emit('close')"><i class="ri-close-line"/></button>
   </div>

   <div :class="['mqtt-connection-state',{online:mqtt.connected&&mqtt.subscribed}]">
    <b class="status-dot"/>{{mqtt.subscribed?'已连接并完成订阅':mqtt.connected?'已连接，正在确认订阅':'当前未连接'}}
    <span>{{mqtt.broker||'尚未配置地址'}}</span>
   </div>

   <form class="mqtt-form" @submit.prevent="save">
    <section class="mqtt-config-section">
     <div class="mqtt-section-heading"><i class="ri-server-line"/><div><h3>Broker 连接</h3><p>服务器、客户端身份和认证信息</p></div></div>
     <div class="form-grid">
      <label class="wide-field">服务端 IP / 主机地址<input v-model.trim="form.host" required maxlength="253" autocomplete="off" placeholder="例如 192.168.31.217"/></label>
      <label>端口<input v-model.number="form.port" type="number" required min="1" max="65535" inputmode="numeric"/></label>
      <label>Client ID<input v-model.trim="form.client_id" required maxlength="100" autocomplete="off"/></label>
      <label>账号<input v-model="form.username" maxlength="100" autocomplete="username" placeholder="可留空"/></label>
      <label>密码
       <div class="password-field"><input v-model="form.password" :type="showPassword?'text':'password'" maxlength="300" autocomplete="new-password" :placeholder="mqtt.config?.password_set?'已设置，留空保持不变':'可留空'"/><button type="button" :aria-label="showPassword?'隐藏密码':'显示密码'" @click="showPassword=!showPassword"><i :class="showPassword?'ri-eye-off-line':'ri-eye-line'"/></button></div>
       <small>{{mqtt.config?.password_set?'后端已有密码；为安全起见不回显明文。':'当前未设置密码。'}}</small>
      </label>
     </div>
     <div class="mqtt-options">
      <label><input v-model="form.tls" type="checkbox"/> TLS 加密</label>
      <label><input v-model="form.autoconnect" type="checkbox"/> 后端启动时自动连接</label>
      <label>QoS<select v-model.number="form.qos"><option :value="0">0</option><option :value="1">1</option><option :value="2">2</option></select></label>
      <label>Keepalive（秒）<input v-model.number="form.keepalive" type="number" min="10" max="3600" required inputmode="numeric"/></label>
     </div>
    </section>

    <section class="mqtt-config-section">
     <div class="mqtt-section-heading"><i class="ri-router-line"/><div><h3>设备与主题</h3><p>ESP32-S3 r19 / V1.1 消息通道</p></div></div>
     <div class="form-grid">
      <label>协议<input v-model="form.protocol" readonly aria-readonly="true"/></label>
      <label>绑定设备编号<input v-model.trim="form.device_id" required maxlength="40"/></label>
      <label class="wide-field">遥测主题<input v-model.trim="form.telemetry_topic" required maxlength="240"/></label>
      <label class="wide-field">控制发布主题<input v-model.trim="form.command_topic" required maxlength="240"/></label>
      <label class="wide-field">指令结果主题<input v-model.trim="form.ack_topic" required maxlength="240"/></label>
      <label class="wide-field">设备状态主题<input v-model.trim="form.state_topic" required maxlength="240"/></label>
      <label class="wide-field">在线状态主题<input v-model.trim="form.availability_topic" required maxlength="240"/></label>
     </div>
     <p class="mqtt-protocol-note"><i class="ri-information-line"/> 当前硬件固定使用 QoS 0 和 <code>tomato_hnsw0001</code> 根主题。修改主题前请同步更新设备端配置。</p>
    </section>

    <div v-if="error" class="error-inline" role="alert">{{error}}</div>
    <div v-if="message" class="mqtt-success" role="status"><i class="ri-checkbox-circle-line"/>{{message}}</div>
    <div class="mqtt-actions">
     <button type="button" :disabled="busy" @click="action('test')"><i class="ri-pulse-line"/> 测试连接</button>
     <button type="button" :disabled="busy||mqtt.connected" @click="action('connect')"><i class="ri-link"/> 连接</button>
     <button type="button" :disabled="busy||!mqtt.connected" @click="action('disconnect')"><i class="ri-link-unlink"/> 断开</button>
     <button class="primary" :disabled="busy">{{busy?'处理中…':'保存配置'}}</button>
    </div>
    <p class="mqtt-action-help">测试和连接使用已保存的配置；修改表单后请先保存。</p>
   </form>
  </aside>
 </div>
</template>
