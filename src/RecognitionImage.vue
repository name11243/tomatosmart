<script setup>
import {ref,watch} from 'vue';
const props=defineProps({source:{type:String,required:true},detections:{type:Array,default:()=>[]}});
const size=ref(null),failed=ref(false);
watch(()=>props.source,()=>{size.value=null;failed.value=false});
function loaded(event){size.value={width:event.target.naturalWidth,height:event.target.naturalHeight}}
</script>

<template>
 <div class="recognition-image">
  <p v-if="failed" role="alert">原图加载失败，请刷新后重试。</p>
  <template v-else>
   <img :src="source" alt="按最低置信度筛选的番茄标注图" @load="loaded" @error="failed=true"/>
   <svg v-if="size" :viewBox="`0 0 ${size.width} ${size.height}`" aria-hidden="true">
    <g v-for="(d,i) in detections" :key="i" class="detection-box" :data-confidence="d.confidence">
     <rect :x="d.box[0]" :y="d.box[1]" :width="d.box[2]-d.box[0]" :height="d.box[3]-d.box[1]" fill="none" stroke="#24ab60" stroke-width="2" vector-effect="non-scaling-stroke"/>
     <text :x="d.box[0]+4" :y="d.box[1]+Math.max(16,size.width/50)" :font-size="Math.max(14,size.width/55)" font-weight="600" fill="white" stroke="#175338" stroke-width="3" paint-order="stroke">{{i+1}} · {{(d.confidence*100).toFixed(1)}}%</text>
    </g>
   </svg>
  </template>
 </div>
</template>

<style scoped>
.recognition-image{position:relative;width:100%;height:300px;line-height:0}
.recognition-image img{display:block;width:100%;height:100%;object-fit:contain}
.recognition-image svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.recognition-image p{padding:20px;line-height:1.6}
@media(max-width:640px){.recognition-image{height:180px}}
</style>
