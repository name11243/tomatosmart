<script setup>
import {nextTick,onBeforeUnmount,onMounted,ref,watch} from 'vue';
import * as echarts from './charts';

const props=defineProps({data:Object});
const emit=defineEmits(['select','source']);
const root=ref();
const immersive=ref(false);
const reducedMotion=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches??false;
let chart;
let observer;
let compactView;

const categoryNames=['主题 / 作物','环境','问题','原因','措施','来源'];
const colors=['#d7efd8','#d8ecf6','#fff0ca','#f7e5b5','#d9eedc','#f7faf8'];
const strokes=['#65a876','#6ca5be','#dca54a','#bd9640','#63a67a','#96aaa5'];
const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

function shortName(node){
 const raw=(node.category===5?node.full_name:node.full_name||node.name||'').replaceAll('\n',' ').trim();
 const limit=node.category===5?18:12;
 const value=raw.length>limit?raw.slice(0,limit-1)+'…':raw;
 if(value.length<=7)return value;
 const breakAt=Math.ceil(value.length/2);
 return value.slice(0,breakAt)+'\n'+value.slice(breakAt);
}

function nodeSize(node,small){
 if(node.category===5)return small?[108,50]:[142,62];
 if(node.category===0)return small?[92,52]:[118,66];
 return small?[84,48]:[104,58];
}

function tooltipText(params){
 if(params.dataType==='edge')return `<b>${escapeHtml(params.data.relation)}</b><br/>${escapeHtml(params.data.source_name)} → ${escapeHtml(params.data.target_name)}`;
 const node=params.data;
 const status=node.category===5?`<br/><span style="color:#687b76">${node.name.includes('待核验')?'待核验资料':'已核验资料'}</span>`:'';
 return `<b>${escapeHtml((node.full_name||node.name).replaceAll('\n',' '))}</b><br/><span style="color:#687b76">${escapeHtml(categoryNames[node.category]||'知识节点')}</span>${status}`;
}

function option(){
 const small=root.value.clientWidth<620;
 const nodes=props.data?.nodes||[];
 const names=Object.fromEntries(nodes.map(node=>[node.id,(node.full_name||node.name).replaceAll('\n',' ')]));
 return {
  animationDuration:reducedMotion?0:500,
  animationDurationUpdate:reducedMotion?0:350,
  tooltip:{trigger:'item',confine:true,appendToBody:immersive.value,formatter:tooltipText,backgroundColor:'#fffffff2',borderColor:'#cdded8',borderWidth:1,textStyle:{color:'#183f38',fontSize:12},extraCssText:'box-shadow:0 10px 30px rgba(20,61,55,.12);border-radius:8px;padding:10px 12px;max-width:280px;white-space:normal;'},
  series:[{
   id:'knowledge-sea',
   type:'graph',
   layout:'force',
   roam:true,
   draggable:true,
   silent:false,
   zoom:small?1.24:.76,
   center:['50%','50%'],
   scaleLimit:{min:.28,max:3.5},
   force:{initLayout:'circular',repulsion:small?1100:1150,gravity:small?.018:.035,edgeLength:small?[135,220]:[145,245],friction:.22,layoutAnimation:!reducedMotion},
   edgeSymbol:['none','arrow'],
   edgeSymbolSize:[0,7],
   lineStyle:{color:'#789590',width:1.1,opacity:.48,curveness:.08},
   label:{show:true,position:'inside',color:'#173f38',fontFamily:'PingFang SC, Microsoft YaHei, sans-serif',fontWeight:600,fontSize:small?10:12,lineHeight:small?14:17,overflow:'break'},
   edgeLabel:{show:false},
   emphasis:{
    focus:'adjacency',
    scale:1.08,
    lineStyle:{opacity:.92,width:2,color:'#3d766b'},
    edgeLabel:{show:true,color:'#274f48',fontSize:small?9:11,backgroundColor:'#fffffff0',borderColor:'#d6e2df',borderWidth:1,borderRadius:4,padding:[4,6],formatter:p=>p.data.relation}
   },
   blur:{itemStyle:{opacity:.18},lineStyle:{opacity:.08},label:{opacity:.22}},
   data:nodes.map(node=>({
    ...node,
    symbol:'roundRect',
    symbolSize:nodeSize(node,small),
    value:node.category,
    itemStyle:{color:colors[node.category]||colors[0],borderColor:strokes[node.category]||strokes[0],borderWidth:1.4,shadowBlur:10,shadowColor:'rgba(32,88,72,.10)'},
    label:{formatter:shortName(node)}
   })),
   links:(props.data?.edges||[]).map((edge,index)=>({
    ...edge,
    relation:edge.label,
    source_name:names[edge.source]||edge.source,
    target_name:names[edge.target]||edge.target,
    label:undefined,
    lineStyle:{curveness:index%2?.09:-.09}
   }))
  }]
 };
}

function render(reset=false){
 if(!chart)return;
 if(!props.data?.nodes?.length){chart.clear();return;}
 if(reset)chart.clear();
 chart.setOption(option(),{notMerge:reset,lazyUpdate:false});
}

function zoom(factor){
 if(!chart)return;
 chart.dispatchAction({type:'graphRoam',seriesId:'knowledge-sea',zoom:factor,originX:root.value.clientWidth/2,originY:root.value.clientHeight/2});
}

function reset(){
 render(true);
 emit('select','视野已复位：拖动空白处移动观察窗，拖动节点可重新排列');
}

async function toggleImmersive(){
 immersive.value=!immersive.value;
 document.body.style.overflow=immersive.value?'hidden':'';
 await nextTick();
 chart?.resize();
}

function keydown(event){
 if(event.key==='Escape'&&immersive.value)toggleImmersive();
}

onMounted(()=>{
 chart=echarts.init(root.value,null,{renderer:'canvas'});
 chart.on('click',params=>{
  if(params.dataType==='edge')emit('select',`${params.data.source_name} —${params.data.relation}→ ${params.data.target_name}`);
  else if(params.dataType==='node'){
   chart.dispatchAction({type:'focusNodeAdjacency',seriesId:'knowledge-sea',dataIndex:params.dataIndex});
   if(params.data.category===5)emit('source',params.data.id);
   else emit('select',(params.data.full_name||params.data.name).replaceAll('\n',' '));
  }
 });
 chart.getZr().on('click',event=>{if(!event.target)chart.dispatchAction({type:'unfocusNodeAdjacency',seriesId:'knowledge-sea'});});
 compactView=root.value.clientWidth<620;
 observer=new ResizeObserver(()=>{
  chart?.resize();
  const nextCompact=root.value.clientWidth<620;
  if(nextCompact!==compactView){compactView=nextCompact;render(true)}
 });
 observer.observe(root.value);
 window.addEventListener('keydown',keydown);
 render(true);
});

watch(()=>props.data,()=>render(true));
onBeforeUnmount(()=>{
 observer?.disconnect();
 window.removeEventListener('keydown',keydown);
 document.body.style.overflow='';
 chart?.dispose();
});

defineExpose({image:()=>chart?.getDataURL({pixelRatio:2,backgroundColor:'#f7fbfa'})});
</script>

<template>
 <div class="graph-observatory" :class="{immersive}">
  <div class="graph-surface">
   <div ref="root" class="graph-canvas" role="img" aria-label="可漫游的番茄种植知识图谱。拖动画布平移，滚轮或双指缩放，节点可以单独拖动。"/>
   <div class="sea-status" aria-hidden="true"><span class="pulse-dot"/>知识海面 <b>{{data?.nodes?.length||0}}</b> 个节点 · <b>{{data?.edges?.length||0}}</b> 条关系</div>
   <div class="graph-hint"><i class="ri-drag-move-2-line"/><span>拖动空白处移动观察窗 · 拖动节点调整位置 · 滚轮或双指缩放</span></div>
   <div class="graph-nav" aria-label="图谱视野控制">
    <button type="button" aria-label="放大图谱" title="放大" @click="zoom(1.22)"><i class="ri-add-line"/></button>
    <button type="button" aria-label="缩小图谱" title="缩小" @click="zoom(.82)"><i class="ri-subtract-line"/></button>
    <button type="button" aria-label="复位图谱视野" title="复位视野" @click="reset"><i class="ri-focus-3-line"/><span>复位</span></button>
    <button type="button" :aria-label="immersive?'退出沉浸观察':'进入沉浸观察'" :title="immersive?'退出沉浸观察':'沉浸观察'" @click="toggleImmersive"><i :class="immersive?'ri-fullscreen-exit-line':'ri-fullscreen-line'"/><span>{{immersive?'退出':'沉浸'}}</span></button>
   </div>
  </div>
 </div>
</template>

<style scoped>
.graph-observatory{height:100%;min-height:0;padding:8px 16px 0}.graph-surface{position:relative;height:100%;min-height:0;overflow:hidden;border:1px solid #d9e8e4;border-radius:14px;background-color:#f5fbfa;background-image:radial-gradient(circle at 22% 18%,#fff 0 2%,transparent 20%),radial-gradient(circle at 82% 78%,#d9f0eb80 0 1%,transparent 27%),linear-gradient(135deg,#fafdff 0%,#eef8f5 48%,#f8fbf7 100%);box-shadow:inset 0 0 70px #8fc3b31c}.graph-surface:before,.graph-surface:after{content:'';position:absolute;pointer-events:none;z-index:1}.graph-surface:before{inset:0;background-image:linear-gradient(#6da9990a 1px,transparent 1px),linear-gradient(90deg,#6da9990a 1px,transparent 1px);background-size:48px 48px;mask-image:linear-gradient(to bottom,#0008,transparent 92%)}.graph-surface:after{width:360px;height:360px;right:-150px;top:-190px;border:1px solid #8fc6b942;border-radius:50%;box-shadow:0 0 0 46px #9bcfc31a,0 0 0 94px #9bcfc30c}.graph-canvas{position:relative;z-index:2;width:100%;height:100%;min-height:420px;touch-action:none}.sea-status,.graph-hint,.graph-nav{position:absolute;z-index:4;background:#fffffff0;border:1px solid #d8e5e1;box-shadow:0 8px 24px #285b4d14;backdrop-filter:blur(8px)}.sea-status{top:14px;left:14px;border-radius:999px;padding:8px 12px;font-size:11px;color:#59736c;display:flex;align-items:center;gap:5px;pointer-events:none}.sea-status b{color:#245f50;font-weight:650}.pulse-dot{width:7px;height:7px;border-radius:50%;background:#52a77e;box-shadow:0 0 0 4px #52a77e1c}.graph-hint{left:50%;bottom:17px;transform:translateX(-50%);border-radius:999px;padding:8px 13px;color:#607770;font-size:11px;display:flex;align-items:center;gap:7px;pointer-events:none;white-space:nowrap}.graph-hint i{font-size:16px;color:#3e806d}.graph-nav{right:14px;bottom:14px;border-radius:9px;display:flex;overflow:hidden}.graph-nav button{min-width:39px;height:39px;padding:0 10px;border:0;border-right:1px solid #e2ebe8;border-radius:0;background:transparent;color:#345f56;font-size:12px}.graph-nav button:last-child{border:0}.graph-nav button:hover{background:#edf6f3}.graph-nav i{font-size:18px}.graph-observatory.immersive{position:fixed;inset:0;z-index:120;padding:18px;background:#e9f4f1}.immersive .graph-surface{border-radius:18px;box-shadow:0 22px 70px #143e3440}.immersive .graph-canvas{min-height:100%}
@media(max-width:700px){.graph-observatory{padding:6px 9px 0}.graph-surface{border-radius:10px}.sea-status{top:9px;left:9px;padding:6px 9px}.graph-hint{left:10px;right:10px;bottom:56px;transform:none;justify-content:center;text-align:center;white-space:normal;padding:6px 9px;font-size:9px}.graph-nav{right:9px;bottom:9px}.graph-nav button{min-width:38px;height:38px;padding:0 8px}.graph-nav button span{display:none}.graph-observatory.immersive{padding:7px}.immersive .graph-surface{border-radius:10px}}
@media(prefers-reduced-motion:reduce){.pulse-dot{box-shadow:none}}
</style>
