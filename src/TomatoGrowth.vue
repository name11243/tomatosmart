<script setup>
import {computed,ref} from 'vue';

const stages=[
 {id:'germination',name:'发芽期',tag:'种子的苏醒',image:'germination.png',width:521,height:431,
  alt:'科普配图：幼芽破土而出，两片子叶展开，茎上仍有种皮',
  intro:'种子吸水后萌发，幼根先伸出，随后幼芽出土、子叶展开。',
  changes:['幼根从种子中伸出，开始吸收水分。','两片子叶展开，为幼苗早期生长提供帮助。','子叶与之后长出的真叶形态不同。'],
  care:'育苗基质保持湿润、透气，避免积水。出苗后及时提供适宜光照，不要强行剥掉仍附着的种皮。',
  observe:'记录出苗日期、子叶展开情况，留意幼茎是否细长倒伏。',
  question:'最先展开的两片叶子，和后来长出的叶子有什么不同？'},
 {id:'seedling',name:'幼苗期',tag:'根与叶的成长',image:'seedling.png',width:444,height:476,
  alt:'科普配图：番茄幼苗长出多片锯齿状真叶，茎秆逐渐直立',
  intro:'真叶陆续长出，根系不断扩展，植株逐步建立吸收与光合作用能力。',
  changes:['真叶逐渐增多，叶缘呈明显的锯齿状。','茎秆逐步变粗，叶片之间的节间伸长。','根系生长，为后续定植和开花积累基础。'],
  care:'提供充足、适宜的光照，保持通风。水培定植时保护根系，结合实际长势管理营养液，避免一次大幅调整浓度。',
  observe:'比较真叶数量、茎秆粗细和叶色，定植时观察根系状态。',
  question:'同样长高的两株幼苗，怎样判断哪一株生长得更健壮？'},
 {id:'flowering',name:'开花坐果期',tag:'从花朵到幼果',image:'flowering.png',width:504,height:477,
  alt:'科普配图：番茄植株开出黄色花朵，花序上同时出现绿色幼果',
  intro:'花蕾开放形成黄色花朵，成功授粉受精后，子房逐渐发育为幼果。',
  changes:['花蕾逐步开放，黄色花瓣向外展开。','授粉受精后，花瓣萎蔫，幼果开始膨大。','同一植株上可能同时出现花蕾、花朵和幼果。'],
  care:'注意通风和温湿度的稳定，观察授粉与坐果情况。温室环境可在适宜条件下轻振花序辅助授粉，避免损伤花朵。',
  observe:'记录开花日期，跟踪同一花序的花朵数量与坐果情况。',
  question:'一朵花开放后，出现哪些变化才说明它开始坐果了？'},
 {id:'fruiting',name:'结果期',tag:'果实膨大与成熟',image:'fruiting.png',width:455,height:444,
  alt:'科普配图：一串番茄果实逐渐膨大，呈现绿色、橙色和红色',
  intro:'果实逐渐膨大并转色，内部糖、有机酸和色素等成分随成熟发生变化。',
  changes:['幼果体积增加，果形逐渐显现。','红果型品种通常由绿色逐步转为橙红色、红色。','不同品种的成熟颜色不同，采收判断应结合品种与用途。'],
  care:'保持水分与营养供应相对稳定，及时支撑结果枝。采收时结合果色、硬度和品种特征判断，避免只凭单一颜色下结论。',
  observe:'跟踪同一果穗的大小与颜色变化，记录转色、成熟和采收日期。',
  question:'同一串番茄为什么会有不同颜色？它们会在同一天成熟吗？'}
];
const selected=ref(0),active=computed(()=>stages[selected.value]);
const tabs=ref([]);
function navigate(event,index){
 let next;
 if(event.key==='ArrowRight')next=(index+1)%stages.length;
 else if(event.key==='ArrowLeft')next=(index+stages.length-1)%stages.length;
 else if(event.key==='Home')next=0;
 else if(event.key==='End')next=stages.length-1;
 else return;
 event.preventDefault();selected.value=next;tabs.value[next]?.focus();
}
</script>

<template>
 <div class="growth-learning">
  <header class="page-heading growth-heading">
   <div><span class="eyebrow">种植科普 · 认识番茄的一生</span><h1>番茄生长周期</h1><p>从一粒种子到一串果实，读懂每个阶段的生长变化。</p></div>
   <span class="growth-label"><i class="ri-book-open-line" aria-hidden="true"/> 生长阶段图解</span>
  </header>

  <div class="growth-intro"><i class="ri-seedling-line" aria-hidden="true"/><p>点击图片了解各阶段。生长速度受品种、温度、光照和栽培方式影响，请以植株的实际变化判断阶段。</p></div>
  <div class="growth-stages" role="tablist" aria-label="番茄生长阶段">
   <button v-for="(stage,index) in stages" :key="stage.id" :ref="el=>tabs[index]=el" type="button" role="tab"
    :id="'growth-tab-'+stage.id" :aria-selected="selected===index" :aria-controls="'growth-panel-'+stage.id"
    :tabindex="selected===index?0:-1" :class="['growth-stage',{selected:selected===index}]"
    @click="selected=index" @keydown="navigate($event,index)">
    <span class="growth-photo"><img :src="'/assets/tomato-growth/'+stage.image" :alt="stage.alt" :width="stage.width" :height="stage.height" decoding="async"/><span class="growth-number">{{String(index+1).padStart(2,'0')}}</span></span>
    <span class="growth-stage-name">{{stage.name}}<i :class="selected===index?'ri-arrow-down-line':'ri-arrow-right-line'" aria-hidden="true"/></span>
    <span class="growth-stage-tag">{{stage.tag}}</span>
   </button>
  </div>

  <section v-for="(stage,index) in stages" :key="stage.id" v-show="selected===index" class="panel growth-detail" role="tabpanel"
   :id="'growth-panel-'+stage.id" :aria-labelledby="'growth-tab-'+stage.id" tabindex="0">
   <div class="growth-detail-heading"><span class="growth-detail-number">{{String(index+1).padStart(2,'0')}}</span><div><h2>{{stage.name}} <span>{{stage.tag}}</span></h2><p>{{stage.intro}}</p></div></div>
   <div class="growth-detail-grid">
    <section><h3><i class="ri-plant-line" aria-hidden="true"/> 植株发生了什么</h3><ul><li v-for="change in stage.changes" :key="change">{{change}}</li></ul></section>
    <section><h3><i class="ri-sun-line" aria-hidden="true"/> 养护关注</h3><p>{{stage.care}}</p></section>
    <section><h3><i class="ri-search-eye-line" aria-hidden="true"/> 可以记录什么</h3><p>{{stage.observe}}</p></section>
   </div>
  </section>

  <aside class="growth-question" aria-label="观察与思考"><i class="ri-lightbulb-line" aria-hidden="true"/><div><h3>带着问题去观察</h3><p>{{active.question}}</p></div></aside>
  <footer class="growth-source"><p>配图：用户提供 · 生长阶段科普素材</p><p>图中土培场景用于展示植株形态。本文为通用科普，不代表当前设备或植株的实测状态；同一株番茄的开花与结果可能重叠。</p></footer>
 </div>
</template>

<style scoped>
.growth-learning{max-width:1440px;margin:0 auto}
.growth-heading{gap:24px}.growth-label{display:inline-flex;align-items:center;gap:8px;flex-shrink:0;font-size:13px;color:var(--green);background:#edf4eb;border:1px solid #dce8da;border-radius:5px;padding:10px 14px}
.growth-intro{display:flex;align-items:flex-start;gap:10px;border-top:1px solid var(--line);padding:16px 0 22px}.growth-intro>i{color:var(--green)}.growth-intro p{font-size:13px}
.growth-stages{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px;margin-bottom:24px}
.growth-stage{display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;gap:0;padding:0 0 16px;overflow:hidden;background:#fffefa;border:1px solid var(--line);border-radius:5px;text-align:left;white-space:normal}
.growth-stage:hover{background:#f4f8f0;border-color:#9cbaa7}.growth-stage.selected{border-color:var(--green);box-shadow:0 0 0 1px var(--green);background:#edf4eb}
.growth-photo{position:relative;display:block;aspect-ratio:6/5;background:#f1eddf;overflow:hidden}.growth-photo img{display:block;width:100%;height:100%;object-fit:contain}.growth-number{position:absolute;top:12px;left:12px;background:#fffefaed;color:#345d44;font-size:12px;font-weight:600;border:1px solid #fff8;border-radius:4px;padding:4px 8px}
.growth-stage-name{display:flex;align-items:center;justify-content:space-between;gap:6px;font-size:17px;font-weight:600;margin:15px 16px 4px}.growth-stage-name i{font-size:19px;color:#638c70}.growth-stage-tag{font-size:12px;color:#708175;margin:0 16px;line-height:1.6}
.growth-detail{padding:24px}.growth-detail-heading{display:flex;gap:16px;align-items:flex-start;padding-bottom:20px;border-bottom:1px solid var(--line)}.growth-detail-number{font-size:32px;line-height:1.4;color:#75a185;font-family:Georgia,serif}.growth-detail-heading h2{font-size:22px}.growth-detail-heading h2 span{display:inline-block;font-size:13px;font-weight:400;color:#7a877e;margin-left:12px}.growth-detail-heading p{font-size:14px;margin-top:6px}
.growth-detail-grid{display:grid;grid-template-columns:1.15fr 1fr 1fr;gap:28px;padding-top:22px}.growth-detail-grid section{min-width:0}.growth-detail-grid h3{display:flex;align-items:center;gap:8px;font-size:15px;margin-bottom:10px}.growth-detail-grid h3 i{color:#61896b;font-size:19px}.growth-detail-grid p,.growth-detail-grid li{font-size:13px;line-height:1.9;color:#64736a}.growth-detail-grid ul{padding-left:18px;margin:0}.growth-detail-grid li+li{margin-top:5px}.growth-detail-grid li::marker{color:#77a285}
.growth-question{display:flex;align-items:flex-start;gap:14px;background:#f4f0e4;border:1px solid #e9e1cc;border-radius:5px;padding:18px 22px;margin-top:20px}.growth-question>i{color:#9b7933;font-size:24px}.growth-question h3{font-size:14px;color:#786337}.growth-question p{font-size:14px;margin-top:4px;color:#75694d}.growth-source{padding:18px 0 8px}.growth-source p{font-size:12px;color:#808b82;line-height:1.8}
@media(max-width:1000px){.growth-stages{gap:14px}.growth-stage-name{font-size:15px;margin-right:12px;margin-left:12px}.growth-stage-tag{margin-right:12px;margin-left:12px}.growth-detail-grid{grid-template-columns:1fr 1fr}.growth-detail-grid section:first-child{grid-column:1/-1}.growth-label{font-size:12px}}
@media(max-width:700px){.growth-stages{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.growth-heading .growth-label{margin-top:14px}.growth-heading{display:block}.growth-photo{aspect-ratio:6/5}.growth-intro{padding-bottom:18px}.growth-detail{padding:20px 16px}.growth-detail-heading{gap:12px}.growth-detail-heading h2{font-size:20px}.growth-detail-heading h2 span{display:block;margin:4px 0 0}.growth-detail-grid{grid-template-columns:1fr;gap:22px}.growth-question{padding:16px}.growth-stage-name{font-size:16px}.growth-detail-heading p{font-size:13px}}
</style>
