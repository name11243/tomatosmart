<script setup>
import {ref,computed,onMounted,watch} from 'vue';
import Graph from './Graph.vue';
import {api,download} from './api';

const props=defineProps({deviceId:String,canTeach:Boolean,canEdit:Boolean});
const emit=defineEmits(['error','notify','screenshot']);
const tab=ref('问答'),question=ref(''),mode=ref('local_ai'),model=ref(''),ai=ref(null),db=ref(null);
const answer=ref(null),all=ref([]),overview=ref(null),history=ref([]),filter=ref(''),graphFilter=ref('');
const busy=ref(false),statusBusy=ref(false),selection=ref('点击节点查看知识，点击来源查看原文'),source=ref(null),record=ref(null);
const editor=ref(null),editorBusy=ref(false),graphBusy=ref(false);
const visible=computed(()=>all.value.filter(k=>JSON.stringify(k).toLowerCase().includes(filter.value.toLowerCase())));
const historyVisible=computed(()=>history.value.filter(k=>JSON.stringify(k).toLowerCase().includes(filter.value.toLowerCase())));
const graphData=computed(()=>answer.value?.graph||overview.value?.graph);
const sourceList=computed(()=>answer.value?.items||overview.value?.items||[]);
async function attempt(fn){emit('error','');try{return await fn()}catch(e){emit('error',e.message)}}
async function statuses(){statusBusy.value=true;try{const results=await Promise.allSettled([api('/ai/status'),api('/knowledge/status')]);
 if(results[0].status==='fulfilled'){ai.value=results[0].value;if(!ai.value.models.includes(model.value))model.value=ai.value.models.includes(ai.value.model)?ai.value.model:(ai.value.models[0]||ai.value.model)}
 else{ai.value={connected:false,models:[],message:results[0].reason.message}}
 if(results[1].status==='fulfilled')db.value=results[1].value;else{db.value={connected:false};emit('error',results[1].reason.message)}
}finally{statusBusy.value=false}}
async function loadOverview(){graphBusy.value=true;try{overview.value=await api('/knowledge/graph?limit=100&q='+encodeURIComponent(graphFilter.value));}catch(e){overview.value=null;throw e}finally{graphBusy.value=false}}
async function load(){all.value=await api('/knowledge');await loadOverview()}
async function query(text){if(busy.value)return;const q=(typeof text==='string'?text:question.value).trim();if(!q){emit('error','请输入种植或设备问题');return}
 question.value=q;busy.value=true;answer.value=null;selection.value='正在检索来源';
 try{await attempt(async()=>{answer.value=await api('/ask',{question:q,device:props.deviceId||'',mode:mode.value,model:model.value});selection.value=answer.value.items.length?'已检索 '+answer.value.items.length+' 条来源，点击节点查看关系':'未找到相关来源';})}finally{busy.value=false}}
function viewSource(id){source.value=sourceList.value.find(k=>k.id===id)||all.value.find(k=>k.id===id)}
function selectNode(text){selection.value=text}
async function switchTab(next){tab.value=next;filter.value='';await attempt(async()=>{if(next==='记录')history.value=await api('/inquiries');if(next==='浏览')all.value=await api('/knowledge')})}
async function save(kind){if(!answer.value)return;await attempt(async()=>{
 await api('/'+kind,kind==='favorites'?{question:answer.value.question,answer_id:answer.value.id}:{title:answer.value.question,answer_id:answer.value.id});
 emit('notify',kind==='favorites'?'当次答案、模型信息与来源快照已收藏':'当次答案与来源快照已保存为探究记录');})}
function startEdit(item){source.value=null;editor.value=item?{...item,tagsText:(item.tags||[]).join('、'),envText:(item.environments||[]).join('、')}:
 {title:'',crop:'番茄',problem:'',cause:'',measure:'',content:'',source:'',tagsText:'',envText:''}}
async function saveKnowledge(){if(editorBusy.value)return;editorBusy.value=true;try{await attempt(async()=>{
 const d=editor.value;const split=text=>[...new Set(text.split(/[、,，\n]/).map(t=>t.trim()).filter(Boolean))];
 await api('/knowledge'+(d.id?'/'+d.id:''),{title:d.title,crop:d.crop,problem:d.problem,cause:d.cause,measure:d.measure,content:d.content,source:d.source,tags:split(d.tagsText),environments:split(d.envText)},d.id?'PUT':'POST');
 editor.value=null;await load();await statuses();emit('notify','资料已写入本地 Python 图谱，标记为待核验；已有问答快照保持原样。');
 })}finally{editorBusy.value=false}}
function answerText(value){return value.generation?value.generation.statements.map(s=>s.text+' ['+s.source_ids.join('、')+']').join('\n\n')+(value.generation.follow_up.length?'\n\n待补充：'+value.generation.follow_up.join('；'):''):value.items.map(k=>k.content+' ['+k.id+']').join('\n\n')||value.message}
async function share(){await attempt(async()=>{const text=answerText(answer.value);if(navigator.share)await navigator.share({title:answer.value.question,text});else{await navigator.clipboard.writeText(text);emit('notify','问答与来源编号已复制')}})}
function fmt(value){return value?new Date(value).toLocaleString('zh-CN'):'—'}
watch(()=>props.deviceId,()=>{if(answer.value)selection.value='答案保留提问时的设备与采样；重新查询可更新上下文'});
onMounted(async()=>{await statuses();await attempt(load)});
</script>

<template>
 <div class="knowledge-workspace">
  <nav class="tabs" aria-label="知识库栏目"><button v-for="t in ['问答','浏览','记录']" :key="t" :class="{selected:tab===t}" @click="switchTab(t)">{{{问答:'知识库与智能问答',浏览:'知识库浏览',记录:'我的探究记录'}[t]}}</button></nav>
  <div class="knowledge-status" aria-live="polite"><span :class="{unavailable:!db?.connected}"><i class="ri-node-tree"/> {{db?.connected?'Python 图谱已就绪 · '+db.sources+' 条资料':'本地图谱加载失败'}}</span><span :class="{unavailable:!ai?.connected}"><i class="ri-cpu-line"/> {{ai?.connected?'Ollama 已连接':'Ollama 未连接'}}</span><button class="text-button" :disabled="statusBusy" @click="statuses">{{statusBusy?'检查中…':'刷新状态'}}</button></div>
  <template v-if="tab==='问答'">
   <section class="knowledge-heading"><h1>从一个问题，开始一次探究</h1><p>本地 AI 结合知识来源整理回答，关系由纯 Python 图谱实时检索。</p></section>
   <form class="question-form" @submit.prevent="query()"><div class="question-input"><i class="ri-search-line"/><input aria-label="输入种植问题" v-model="question" maxlength="1000" placeholder="输入种植或设备问题，如 MQTT 使用哪些主题？"/></div><button class="primary search-button" :disabled="busy||!question.trim()">{{busy?'查询中…':'查询'}}</button></form>
   <div class="query-options"><label>回答方式 <select v-model="mode" :disabled="busy"><option value="local_ai">本地 AI + 知识来源</option><option value="python_graph">仅查询知识资料</option></select></label><label v-if="mode==='local_ai'">本地模型 <select v-model="model" :disabled="busy||!ai?.models?.length"><option v-for="m in ai?.models" :key="m" :value="m">{{m}}</option><option v-if="!ai?.models?.length" :value="model">暂无可用模型</option></select></label><small v-if="busy" role="status">正在检索并整理回答，首次加载本地模型可能需要较长时间。</small><small v-else-if="mode==='local_ai'&&!ai?.connected">{{ai?.message}} 可选择仅查询知识资料。</small></div>
   <div class="knowledge-grid">
    <section class="panel graph-panel"><div class="panel-heading"><div><span class="eyebrow">KNOWLEDGE OCEAN</span><h2>知识图谱观察窗</h2><p>{{answer?'本次问题的来源关系 · 节点仍可自由拖动':'完整知识海面 · 移动观察窗探索全部关系，也可筛选聚焦'}}</p></div><button v-if="answer" class="text-button" @click="answer=null;attempt(loadOverview)">返回完整图谱</button></div>
     <form v-if="!answer" class="graph-filter" @submit.prevent="attempt(loadOverview)"><input v-model="graphFilter" aria-label="筛选图谱" placeholder="按标题、问题或来源筛选图谱"/><button :disabled="graphBusy">筛选</button></form>
     <div class="legend"><span v-for="(label,i) in ['主题 / 作物','环境','问题','原因','措施','来源']" :key="label"><b :class="'dot dot-'+i"/>{{label}}</span></div>
     <Graph v-if="graphData?.nodes?.length" :data="graphData" @select="selectNode" @source="viewSource"/>
     <div v-else class="empty graph-empty"><i class="ri-node-tree"/><p>{{busy?'正在检索知识关系…':db?.connected?(answer?'没有与此问题匹配的关系。':'暂无匹配资料。新增实际来源后即可建立图谱。'):'本地图谱加载失败，请检查知识文件。'}}</p><button v-if="canTeach&&!answer" @click="startEdit()">新增知识资料</button></div>
     <div class="relation">{{selection}}<span v-if="!answer&&overview"> · {{overview.items.length}} / {{overview.total}} 条资料</span></div>
    </section>
    <section class="panel answer-panel" aria-live="polite" :aria-busy="busy"><div class="answer-top"><h2>{{answer?.generation?'本地 AI 回答':'知识检索'}}</h2><span>{{answer?.generation?.model||'保留资料原文与真实性标记'}}</span></div>
     <template v-if="answer?.generation"><p class="answer-notice">{{answer.generation.notice}}</p><article v-for="(s,i) in answer.generation.statements" :key="i" class="answer-item"><p class="preserve-text">{{s.text}}</p><div class="citation-row"><button v-for="id in s.source_ids" :key="id" class="source-chip" @click="viewSource(id)">{{id}}</button></div></article><section v-if="answer.generation.follow_up.length" class="measures"><h3>还需补充的观察或资料</h3><p v-for="s in answer.generation.follow_up" :key="s">{{s}}</p></section></template>
     <template v-if="answer?.items.length"><details :open="!answer.generation" class="retrieved-sources"><summary>查看 {{answer.items.length}} 条检索来源</summary><article v-for="k in answer.items" :key="k.id" class="answer-item"><h3>{{k.title}}</h3><p>{{k.cause}}；{{k.measure}}</p><div class="citation-row"><button class="source-chip" @click="viewSource(k.id)">{{k.id}}</button><small>{{k.verified?'已核验资料':'待核验资料'}} · {{k.source}}</small></div></article></details><div class="answer-actions"><button class="primary" :disabled="!canEdit" @click="save('inquiries')">保存为探究记录</button><button :disabled="!canEdit" @click="save('favorites')">收藏答案</button><button @click="share">分享问答</button></div></template>
     <div v-else class="empty"><i class="ri-search-eye-line"/><p>{{busy?'本地查询进行中…':answer?.message||'输入问题开始查询，或点击左侧图谱追溯来源。'}}</p><p v-if="!answer&&!busy">种植诊断需有实际资料与观察依据，设备接入资料不能替代农艺知识。</p></div>
     <p v-if="answer" class="context-note">提问时间：{{fmt(answer.created_at)}} · {{answer.device?'设备 '+answer.device+' / '+answer.batch:'未关联设备'}}<br/>{{answer.environment?'关联采样：'+fmt(answer.environment.ts)+(answer.environment.is_stale?'（已过期，仅供历史参考）':'（提问时采样快照）'):'未关联环境采样，不据此推断当前植株状态。'}}</p>
    </section>
   </div><div class="knowledge-secondary"><span>资料、图谱、模型回答分别保留来源与快照</span><button class="text-button" v-if="canEdit" @click="emit('screenshot')">保存问答截图</button></div>
  </template>
  <template v-else>
   <div class="page-heading"><div><h1>{{tab==='浏览'?'知识库浏览':'我的探究记录'}}</h1><p>{{tab==='浏览'?'录入实际资料，维护问题、原因、措施及明确提及的环境因素。':'回看当次回答、模型和来源快照。'}}</p></div><button v-if="tab==='浏览'&&canTeach" class="primary" @click="startEdit()">新增知识资料</button><button v-if="tab==='记录'" @click="download('inquiries','pdf')">导出探究报告</button></div>
   <input class="filter-input" v-model="filter" aria-label="搜索知识记录" placeholder="搜索标题、内容或来源编号"/>
   <div class="document-list"><article v-for="k in tab==='浏览'?visible:historyVisible" :key="k.id"><div><span class="eyebrow">{{k.id}} · {{tab==='浏览'?(k.verified?'已核验资料':'待核验资料'):fmt(k.created_at)}}</span><h3>{{k.title}}</h3><p class="preview-content">{{k.content}}</p><small>{{k.source}}</small></div><div class="actions"><button @click="tab==='浏览'?source=k:record=k">查看详情</button><button v-if="tab==='浏览'&&canTeach" @click="startEdit(k)">编辑</button><button v-if="tab==='浏览'" @click="tab='问答';query(k.problem)">查询相关知识</button></div></article><div v-if="!(tab==='浏览'?visible:historyVisible).length" class="empty">没有匹配记录。</div></div>
  </template>

  <div v-if="source||record" class="modal-backdrop" @click.self="source=null;record=null"><section class="modal knowledge-dialog" role="dialog" aria-modal="true" aria-label="知识来源详情"><div class="row-between"><h2>{{(source||record).title}}</h2><button aria-label="关闭详情" @click="source=null;record=null">关闭</button></div><template v-if="source"><p>{{source.id}} · {{source.verified?'已核验资料':'待核验资料'}}<br/>来源：{{source.source}}</p><p class="preserve-text">{{source.content}}</p><p v-if="source.source_sha256" class="hash-note">原文件 SHA-256：{{source.source_sha256}}</p><p v-if="source.revisions?.length">已保留 {{source.revisions.length}} 个历史版本；既有问答保存各自引用原文。</p><button v-if="canTeach" @click="startEdit(source)">编辑资料</button></template><template v-else><p class="preserve-text">{{record.content}}</p><template v-if="record.answer"><p>模型：{{record.answer.generation?.model||'仅资料查询'}} · {{fmt(record.answer.created_at)}}</p><details v-for="k in record.answer.items" :key="k.id"><summary>{{k.id}} · {{k.title}} · {{k.verified?'已核验':'待核验'}}</summary><p class="preserve-text">{{k.content}}</p><small>{{k.source}}</small></details></template></template></section></div>
  <div v-if="editor" class="modal-backdrop"><form class="modal knowledge-dialog" role="dialog" aria-modal="true" aria-label="编辑知识资料" @submit.prevent="saveKnowledge"><h2>{{editor.id?'编辑知识资料':'新增知识资料'}}</h2><p>仅填写有实际依据的内容；新建或编辑均标记为待核验，历史引用保持原样。</p><div class="knowledge-fields"><label v-for="f in [['title','标题',200],['crop','主题 / 作物',100],['problem','问题 / 主题',300],['cause','原因 / 关系说明',500],['measure','措施 / 核对方法',1000],['source','来源说明或链接',1000]]" :key="f[0]">{{f[1]}}<input v-model="editor[f[0]]" required :maxlength="f[2]"/></label><label>关键词（顿号分隔）<input v-model="editor.tagsText" maxlength="500"/></label><label>原文明示的环境因素（可留空）<input v-model="editor.envText" maxlength="300" placeholder="如 EC、液位；未提及则留空"/></label></div><label>资料正文<textarea v-model="editor.content" required maxlength="20000" rows="8"/></label><div class="actions"><button type="button" :disabled="editorBusy" @click="editor=null">取消</button><button class="primary" :disabled="editorBusy">{{editorBusy?'保存中…':'保存到本地图谱'}}</button></div></form></div>
 </div>
</template>

<style scoped>
.modal-backdrop{position:fixed;inset:0;z-index:60;background:#14352666;display:flex;align-items:center;justify-content:center}.graph-panel{display:flex;flex-direction:column;height:clamp(760px,86vh,980px);min-height:0;overflow:visible}.graph-panel .panel-heading{height:auto;flex-shrink:0;padding-bottom:12px}.graph-panel :deep(.graph-observatory){height:auto;flex:1;min-height:520px}.graph-panel .relation{position:static;max-width:none;font-size:11px;padding:12px 20px;white-space:normal;border-top:1px solid var(--line);color:#61736d}.answer-panel{height:auto;min-height:0}.query-options select{width:auto}.knowledge-grid{grid-template-columns:minmax(0,1fr);align-items:start;gap:18px}.knowledge-status button{font-size:12px}.graph-panel .legend{padding-bottom:7px}.graph-panel .eyebrow{display:block;margin-bottom:3px;color:#559079;font-size:10px;letter-spacing:1.5px}
.knowledge-status,.query-options{display:flex;flex-wrap:wrap;align-items:center;gap:12px 22px;font-size:12px;color:var(--green);padding:12px 0}.knowledge-status{border-bottom:1px solid var(--line)}.unavailable{color:#9a6727}.query-options{padding:0 0 22px;color:#607470}.query-options label{display:flex;gap:8px;align-items:center}.graph-filter{display:flex;gap:8px;padding:0 22px 12px}.graph-filter input{width:100%;min-width:0}.legend{padding:0 22px;flex-wrap:wrap}.graph-empty{min-height:350px;display:flex;align-items:center;justify-content:center;flex-direction:column}.answer-notice,.context-note{font-size:12px;color:#687972;padding:12px 0;line-height:1.8}.context-note{border-top:1px solid var(--line);margin-top:16px}.preserve-text{white-space:pre-wrap;overflow-wrap:anywhere}.retrieved-sources{padding-top:15px}.retrieved-sources summary{cursor:pointer;color:var(--green)}.preview-content{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.knowledge-dialog{max-width:760px;width:calc(100% - 32px);max-height:88vh;overflow:auto;display:grid;gap:18px}.knowledge-fields{display:grid;grid-template-columns:1fr 1fr;gap:14px}.knowledge-dialog label{display:grid;gap:6px;font-size:13px}.knowledge-dialog input,.knowledge-dialog textarea{width:100%;min-width:0}.hash-note{font-size:11px;overflow-wrap:anywhere}.knowledge-dialog details{padding:12px 0}.dot-5{background:#f4f8fa;border:1px solid #879e9b}.citation-row{overflow-wrap:anywhere}.source-chip{max-width:100%;white-space:normal;overflow-wrap:anywhere}.document-list .actions{flex-wrap:wrap;flex-shrink:0}.answer-actions{flex-wrap:wrap}
@media(max-width:650px){.knowledge-fields{grid-template-columns:1fr}.document-list article{flex-direction:column;align-items:stretch}.knowledge-status{gap:10px}.query-options label{width:100%;justify-content:space-between}.query-options select{max-width:70%}.graph-filter{padding:0 14px 10px}.legend{gap:9px 12px;padding:0 14px}.knowledge-secondary{align-items:flex-start;gap:8px}.graph-empty{min-height:240px}.graph-panel{height:620px}.graph-panel .panel-heading{padding-bottom:9px}.graph-panel :deep(.graph-observatory){min-height:390px}.graph-panel .relation{padding:9px 14px}}
</style>
