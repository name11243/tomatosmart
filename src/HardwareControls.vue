<script setup>
import {computed,reactive,ref,watch} from 'vue';
const props=defineProps({device:{type:Object,required:true},connected:Boolean,canEdit:Boolean,canTeach:Boolean,busy:Boolean});
const emit=defineEmits(['command']);
const state=computed(()=>props.device.device_state);
const ready=computed(()=>props.connected&&props.device.online&&!!state.value&&!props.busy);
const manual=computed(()=>state.value?.control_mode===0);
const command=ref('05'),form=reactive({value:null,start_hour:null,start_minute:null,end_hour:null,end_minute:null});
const stages=['出苗','壮苗','营养生长','开花 / 坐果','果实膨大'];
const settings=[
 {cmd:'01',field:'red_brightness',label:'红灯亮度',min:0,max:100,unit:'%',manual:true},
 {cmd:'02',field:'blue_brightness',label:'蓝灯亮度',min:0,max:100,unit:'%',manual:true},
 {cmd:'05',field:'fill_light_mode',label:'补光阶段',min:1,max:5},
 {cmd:'06',field:'pump_interval_min',label:'泵运行间隔',min:0,max:65535,unit:'分钟'},
 {cmd:'07',field:'pump_duration_sec',label:'泵运行时长',min:0,max:65535,unit:'秒'},
 {cmd:'09',field:'rest_schedule',label:'休息时段'}
];
const selected=computed(()=>settings.find(item=>item.cmd===command.value));
const timeFields=[['start_hour','开始时'],['start_minute','开始分'],['end_hour','结束时'],['end_minute','结束分']];
const settingReady=computed(()=>ready.value&&props.canEdit&&(!selected.value.manual||manual.value));
function loadSetting(){
 const current=state.value?.[selected.value.field];
 if(command.value==='09')for(const [key] of timeFields)form[key]=current?.[key]??null;
 else form.value=current??null;
}
watch(command,loadSetting);
watch(()=>props.device.id,loadSetting);
function submit(){
 if(!settingReady.value)return;
 const data=command.value==='09'?Object.fromEntries(timeFields.map(([key])=>[key,Number(form[key])])):{value:Number(form.value)};
 const label=command.value==='09'?`休息时段 ${String(data.start_hour).padStart(2,'0')}:${String(data.start_minute).padStart(2,'0')}–${String(data.end_hour).padStart(2,'0')}:${String(data.end_minute).padStart(2,'0')}`:`${selected.value.label}：${command.value==='05'?stages[data.value-1]:data.value+(selected.value.unit||'')}`;
 emit('command',{cmd:command.value,data,label});
}
</script>

<template>
 <section class="panel control-panel hardware-controls">
  <div class="panel-heading"><div><h2>设备控制</h2><p>{{!state?'等待设备状态':manual?'手动模式':'设备 AI 智控'}}</p></div><button v-if="canTeach" :disabled="!ready" @click="emit('command',{cmd:'08',data:{value:manual?1:0},label:manual?'切换为设备 AI 智控':'切换为手动模式'})">{{manual?'切换 AI 智控':'切换手动'}}</button></div>
  <div class="actuator" v-for="item in [{cmd:'03',key:'pump_state',name:'雾化泵',icon:'water-flash-line'},{cmd:'04',key:'light_master_state',name:'补光灯总开关',icon:'lightbulb-line'}]" :key="item.cmd">
   <i :class="'ri-'+item.icon"/><div><h3>{{item.name}}</h3><p>{{!state?'状态未知':state[item.key]?'设备报告：开启':'设备报告：关闭'}}</p></div>
   <button role="switch" :aria-label="item.name" :aria-checked="state?!!state[item.key]:'false'" :class="['toggle',{on:state?.[item.key]}]" :disabled="!canEdit||!ready||!manual" @click="emit('command',{cmd:item.cmd,data:{value:state[item.key]?0:1},label:(state[item.key]?'关闭':'开启')+item.name})"><span/></button>
  </div>
  <dl class="hardware-state"><div><dt>红灯 / 蓝灯</dt><dd>{{state?state.red_brightness+'% / '+state.blue_brightness+'%':'—'}}</dd></div><div><dt>补光阶段</dt><dd>{{state?stages[state.fill_light_mode-1]:'—'}}</dd></div><div><dt>泵间隔 / 时长</dt><dd>{{state?state.pump_interval_min+' 分钟 / '+state.pump_duration_sec+' 秒':'—'}}</dd></div><div><dt>休息时段</dt><dd>{{state?String(state.rest_schedule.start_hour).padStart(2,'0')+':'+String(state.rest_schedule.start_minute).padStart(2,'0')+'–'+String(state.rest_schedule.end_hour).padStart(2,'0')+':'+String(state.rest_schedule.end_minute).padStart(2,'0'):'—'}}<small v-if="state?.rest_schedule.crosses_midnight">（跨天）</small></dd></div></dl>
  <p class="muted">{{!connected?'平台尚未连接设备服务。':!device.online?'等待设备实时上报，暂不可下发控制。':!state?'等待设备控制状态，暂不可下发控制。':!manual?'AI 智控由设备运行，直接开关和亮度调节仅在手动模式可用。':'操作结果以设备回执为准，开关状态由设备主动上报。'}}</p>
  <details v-if="canEdit" class="hardware-settings" @toggle="event=>{if(event.target.open)loadSetting()}"><summary>亮度与运行设置</summary><form @submit.prevent="submit">
   <label>设置项目<select v-model="command" aria-label="设备设置项目"><option v-for="item in settings" :key="item.cmd" :value="item.cmd">{{item.label}}</option></select></label>
   <div v-if="command==='09'" class="hardware-time"><label v-for="[key,label] in timeFields" :key="key">{{label}}<input v-model.number="form[key]" type="number" min="0" :max="key.endsWith('hour')?23:59" step="1" required :aria-label="label"/></label></div>
   <label v-else-if="command==='05'">目标阶段<select v-model.number="form.value" required aria-label="目标补光阶段"><option :value="null" disabled>选择补光阶段</option><option v-for="(stage,index) in stages" :value="index+1">{{stage}}</option></select></label>
   <label v-else>{{selected.label}}（{{selected.unit}}）<input v-model.number="form.value" type="number" :min="selected.min" :max="selected.max" step="1" required :aria-label="selected.label"/></label>
   <button class="primary" :disabled="!settingReady" type="submit">确认设置</button>
  </form></details>
 </section>
</template>

<style scoped>
.hardware-controls{scroll-margin-top:80px}
.hardware-state{margin:14px 20px;display:grid;gap:10px;font-size:12px}.hardware-state>div{display:flex;justify-content:space-between;gap:12px}.hardware-state dt{color:#78838a}.hardware-state dd{margin:0;text-align:right}.hardware-settings{margin:18px 20px 0;border-top:1px solid #e2e6e2;padding-top:14px}.hardware-settings summary{cursor:pointer;font-size:13px}.hardware-settings form{margin-top:14px;display:grid;gap:12px}.hardware-settings label{font-size:12px;display:grid;gap:7px}.hardware-settings select,.hardware-settings input{font-size:13px;padding:8px}.hardware-time{display:grid;grid-template-columns:1fr 1fr;gap:10px}.hardware-settings button{justify-self:end}.hardware-controls .panel-heading>button{font-size:12px;padding:7px 9px}
</style>
