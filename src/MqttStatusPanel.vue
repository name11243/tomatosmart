<script setup>
defineProps({mqtt:{type:Object,required:true},device:{type:Object,default:()=>({})},metrics:{type:Array,default:()=>[]}});
function fmt(t){return t?new Date(t).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'—'}
</script>

<template>
 <section class="mqtt-status-panel">
  <div class="mqtt-status-heading">
   <div><b :class="['status-dot',{online:mqtt.connected&&mqtt.subscribed}]"/>{{mqtt.subscribed?'本机 MQTT 已连接并完成订阅':mqtt.connected?'正在确认订阅':'本机 MQTT 未连接'}}</div>
   <span v-if="device.id">设备通信{{device.online?'在线':'离线 / 等待遥测'}} · 每 {{mqtt.telemetry_interval_seconds||15}} 秒上报</span>
  </div>
  <p v-if="mqtt.error">{{mqtt.error}}</p>
  <p v-if="device.latest&&device.unavailable_metrics?.length">{{device.online?'最新上报':'最近一次上报'}}中 {{device.unavailable_metrics.length}} 项传感器暂无读数：{{metrics.filter(m=>device.unavailable_metrics.includes(m[0])).map(m=>m[1]).join('、')}}。请检查传感器连接或设备采集状态。</p>
  <details>
   <summary>查看通信状态</summary>
   <dl>
    <div><dt>平台连接</dt><dd>{{mqtt.broker}}</dd></div>
    <div><dt>发布控制</dt><dd>{{mqtt.publish_topic}} · QoS {{mqtt.publish_qos}}</dd></div>
    <div v-for="subscription in mqtt.subscriptions" :key="subscription.topic"><dt>订阅</dt><dd>{{subscription.topic}} · QoS {{subscription.qos}}</dd></div>
    <div><dt>最近收到消息</dt><dd>{{fmt(mqtt.received_at)}}</dd></div>
   </dl>
  </details>
 </section>
</template>
