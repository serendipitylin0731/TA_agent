const app = document.getElementById('app');
const SUBJECTS = ['全部学科','语文','数学','英语','物理','化学','生物学','道德与法治','思想政治','历史','地理','信息技术','通用技术'];
const EXAMPLES = [
  '函数的定义是什么？','一次函数和反比例函数有什么区别？','勾股定理适用于什么三角形？',
  '光合作用的基本过程是什么？','细胞膜有什么作用？','牛顿第一定律讲的是什么？',
  '电流、电压和电阻有什么关系？','酸和碱发生中和反应时会怎样？','中国古代科举制度怎样发展？',
  '近代中国社会发生了哪些变化？','地形对气候有什么影响？','如何理解依法治国？',
  '《济南的冬天》描写了哪些景物？','英语一般过去时怎样使用？','算法和程序有什么区别？',
  '设计的一般原则有哪些？','生态系统中的能量如何流动？','为什么会形成季风？',
  '椭圆的第二定义是什么？','欧姆定律如何应用于串联电路？','地球自转会带来哪些现象？',
  '《背影》的作者是谁？','辛亥革命有什么历史意义？','减数分裂的主要阶段有哪些？',
  '酸碱中和反应生成什么？','秦朝统一采取了哪些措施？','水循环有哪些主要环节？',
  '算法有哪些基本特征？','设计时如何兼顾实用与可持续发展？','英语现在完成时与一般过去时有何区别？'
];
const sampleExamples = (previous=[]) => {
  const pool=EXAMPLES.filter(question=>!previous.includes(question));
  for(let i=pool.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[pool[i],pool[j]]=[pool[j],pool[i]]}
  return pool.slice(0,4);
};
const readHistory = key => {try {const value=JSON.parse(localStorage.getItem(key)||'[]');return Array.isArray(value)?value.slice(-10):[]} catch {return []}};
const newId = () => crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
const oldChatMessages=readHistory('ta-chat-v2').flatMap(item=>item.messages||[]);
const savedChatSessions=readHistory('ta-chat-sessions-v1');
const savedSearchSessions=readHistory('ta-search-sessions-v1');
const state = {view:'chat',stage:'',subject:'',searchQuery:'',searchResults:[],searchSuggestions:{completions:[],corrections:[]},searchCorrected:'',catalog:[],sources:[],status:null,messages:[],chatSessions:savedChatSessions.length?savedChatSessions:oldChatMessages.length?[{id:newId(),title:oldChatMessages[0]?.content?.slice(0,26)||'此前对话',messages:oldChatMessages,stage:'',subject:'',updatedAt:Date.now()}]:[],searchSessions:savedSearchSessions.length?savedSearchSessions:readHistory('ta-search-v2').map(item=>({id:newId(),title:item.query,query:item.query,stage:item.stage,subject:item.subject,results:[],corrected:'',updatedAt:Date.now()})),activeChatId:null,activeSearchId:null,busy:false,notice:'',reader:null,readerReturn:null,catalogSelection:null,examples:sampleExamples()};
const saveHistory = (key,items) => {try {localStorage.setItem(key,JSON.stringify(items.slice(-10)))} catch {}};
const saveSessions = () => {saveHistory('ta-chat-sessions-v1',state.chatSessions);saveHistory('ta-search-sessions-v1',state.searchSessions)};
function newChat(){state.view='chat';state.activeChatId=null;state.messages=[];state.stage='';state.subject='';state.examples=sampleExamples(state.examples);state.notice='';render()}
function newSearch(){state.view='search';state.activeSearchId=null;state.searchQuery='';state.searchResults=[];state.searchCorrected='';state.searchSuggestions={completions:[],corrections:[]};state.stage='';state.subject='';state.notice='';render()}
function openChatSession(id){const session=state.chatSessions.find(item=>item.id===id);if(!session)return;state.view='chat';state.activeChatId=id;state.messages=[...session.messages];state.stage=session.stage||'';state.subject=session.subject||'';render()}
function openSearchSession(id){const session=state.searchSessions.find(item=>item.id===id);if(!session)return;state.view='search';state.activeSearchId=id;state.searchQuery=session.query;state.searchResults=session.results||[];state.searchCorrected=session.corrected||'';state.stage=session.stage||'';state.subject=session.subject||'';render()}

const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const api = async (path, options={}) => {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `请求失败 (${response.status})`);
  return data;
};
const post = (path, value) => api(path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
const icon = (name,size=19) => {
  const p={spark:'<path d="m12 2 1.9 6.1L20 10l-6.1 1.9L12 18l-1.9-6.1L4 10l6.1-1.9L12 2Z"/><path d="m19 17 .5 1.5L21 19l-1.5.5L19 21l-.5-1.5L17 19l1.5-.5L19 17Z"/>',search:'<circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4.5 4.5"/>',book:'<path d="M4 5.5c3.1-1.3 5.8-1.3 8 0v14c-2.2-1.3-4.9-1.3-8 0zM12 5.5c2.2-1.3 4.9-1.3 8 0v14c-3.1-1.3-5.8-1.3-8 0z"/>',layers:'<path d="m12 3 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 16l9 5 9-5"/>',arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',external:'<path d="M13 5h6v6M19 5l-9 9M19 14v5H5V5h5"/>',plus:'<path d="M12 5v14M5 12h14"/>',close:'<path d="M5 5l14 14M19 5 5 19"/>',send:'<path d="m3 11 18-8-8 18-2.6-7.4L3 11ZM10.4 13.6 21 3"/>',shield:'<path d="m12 2 8 3v6c0 5-3.4 8.4-8 11-4.6-2.6-8-6-8-11V5l8-3Z"/><path d="m9 12 2 2 4-4"/>',pin:'<path d="M12 21s7-5 7-12a7 7 0 1 0-14 0c0 7 7 12 7 12Z"/><circle cx="12" cy="9" r="2"/>',globe:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 4 6 4 9s-1 6-4 9M12 3c-3 3-4 6-4 9s1 6 4 9"/>',filter:'<path d="M4 6h16M7 12h10M10 18h4"/>',upload:'<path d="M12 16V4m-4 4 4-4 4 4M4 17v3h16v-3"/>',check:'<path d="m4 12 5 5L20 6"/>',user:'<circle cx="12" cy="8" r="3.5"/><path d="M4.5 20c.5-3.8 3-6 7.5-6s7 2.2 7.5 6"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'};
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p[name]||p.book}</svg>`;
};
const titleMap = {chat:['Chat 问答','教材优先，给出清楚直接的回答'],search:['查询原文','检索并在页面内阅读教材原文'],catalog:['阅读原版教材','选择学段、学科和册次，阅读原版 PDF']};

function render() {
  if(state.view==='reader' && state.reader){app.innerHTML=readerView();bind();return}
  const title=titleMap[state.view];
  app.innerHTML=`<div class="shell ${state.view==='chat'?'chat-shell':''} ${state.view==='chat'&&(state.messages.length||state.busy)?'chat-active':''}">
    <aside class="sidebar"><div class="brand"><div class="brand-icon"><img src="/logo.svg" alt=""></div><div><strong>知页 <em>TA</em></strong><small>TEACHING ATLAS AGENT</small></div></div>
      <div class="nav-label">工作空间</div><nav aria-label="主导航">
        ${[['chat','spark','Chat 问答'],['search','search','查询原文'],['catalog','book','阅读教材']].map(([key,ic,label])=>`<button class="nav-item ${state.view===key?'active':''}" data-view="${key}">${icon(ic,18)}<span>${label}</span></button>`).join('')}
      </nav><button class="history-toggle" data-toggle-history aria-label="查看最近记录">${icon('clock',19)}</button><div class="sidebar-history-scroll"><div class="sidebar-history-head"><span>最近对话</span><button data-new-chat aria-label="新建聊天">${icon('plus',14)}</button></div><div class="sidebar-history-items">${[...state.chatSessions].reverse().slice(0,10).map(item=>`<button class="sidebar-history-item ${state.activeChatId===item.id&&state.view==='chat'?'selected':''}" data-chat-session="${esc(item.id)}" title="${esc(item.title)}">${icon('clock',14)}<span>${esc(item.title)}</span></button>`).join('')||'<small>暂无对话</small>'}</div><div class="sidebar-history-head"><span>最近检索</span><button data-new-search aria-label="新建检索">${icon('plus',14)}</button></div><div class="sidebar-history-items">${[...state.searchSessions].reverse().slice(0,10).map(item=>`<button class="sidebar-history-item ${state.activeSearchId===item.id&&state.view==='search'?'selected':''}" data-search-session="${esc(item.id)}" title="${esc(item.title)}">${icon('search',14)}<span>${esc(item.title)}</span></button>`).join('')||'<small>暂无检索</small>'}</div></div><div class="sidebar-grow"></div><a class="sidebar-card" href="/about.html"><span class="orb">${icon('shield',18)}</span><strong>有据可查，才值得相信</strong><p>了解设计初衷、功能与教材覆盖 →</p></a><a class="sidebar-foot" href="mailto:serendipity_lin@sjtu.edu.cn">有问题请联系<br>serendipity_lin@sjtu.edu.cn</a></aside>
    <main class="main"><header class="topbar"><span>教学知识工作台 <b>/</b> ${title[0]}</span><div class="top-status"><span class="tiny-dot"></span>${state.status?.deepseek_configured?'AI 问答已就绪':'AI 问答待配置'}</div></header>
      <div class="page"><div class="heading"><div><div class="eyebrow"><span></span> EVIDENCE FIRST LEARNING <span></span></div><h1>${title[0]}<i>.</i></h1><p>${title[1]}</p></div></div>
      ${state.view==='chat'?chatView():state.view==='search'?searchView():catalogView()}
      <footer class="footer"><span>知页 TA Agent · 教学研究原型</span><span>回答可能有误，请以原始资料与教师核验为准</span></footer></div>
    </main>${state.notice?`<div class="toast" role="status">${esc(state.notice)}</div>`:''}</div>`;
  bind();
  if(state.view==='chat')window.scrollTo(0,0);
  if(window.renderMathInElement)document.querySelectorAll('.message-bubble').forEach(el=>window.renderMathInElement(el,{delimiters:[{left:'$$',right:'$$',display:true},{left:'\\[',right:'\\]',display:true},{left:'\\(',right:'\\)',display:false}],throwOnError:false}));
  if(state.view==='chat'&&state.messages.length)requestAnimationFrame(()=>{const body=document.getElementById('chatBody');if(body)body.scrollTop=body.scrollHeight});
}

function filters() {
  return `<div class="filters"><label>学段<select id="stageFilter"><option value="">全部学段</option><option value="初中" ${state.stage==='初中'?'selected':''}>初中</option><option value="高中" ${state.stage==='高中'?'selected':''}>高中</option></select></label><label>学科<select id="subjectFilter">${SUBJECTS.map((s,i)=>`<option value="${i?s:''}" ${state.subject===(i?s:'')?'selected':''}>${s}</option>`).join('')}</select></label></div>`;
}
function sourceBadge() {return '<span class="badge textbook">教材原件</span>';}
function locator(item) {return item.page?`PDF 第 ${item.page} 页`:'文档';}
function resultCard(item,index) {
  return `<button class="result-card" data-open-result="${index}"><div class="result-top">${sourceBadge(item.kind)}<span class="result-meta">${esc(item.stage)} · ${esc(item.subject)}</span></div><h3>${esc(item.title)}</h3><p>${esc(item.snippet)}</p><div class="key-pages"><strong>关键页码</strong>${(item.key_pages||[]).map(p=>`<span>第 ${p.page} 页</span>`).join('')}</div><div class="result-bottom"><span>${icon('pin',14)} ${esc(item.volume||item.edition||'教材')} · ${locator(item)}</span><span>点击整张卡片阅读 ${icon('arrow',14)}</span></div></button>`;
}
function readerView() {
  const r=state.reader;
  const s=r.source;
  const backLabel={chat:'Chat 问答',search:'查询原文',catalog:'阅读教材'}[state.readerReturn?.view]||'上一页';
  return `<div class="reader-screen"><header class="reader-toolbar"><button class="reader-back" data-close-reader>${icon('arrow',17)} 返回 ${backLabel}</button><div class="reader-brand">知页 <span>· 双页阅读</span></div>${s.url?`<a class="reader-origin" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">资料来源 ${icon('external',15)}</a>`:''}</header><div class="reader-summary">${sourceBadge(s.kind)}<div><h1>${esc(s.title)}</h1><p>${esc([s.stage,s.subject,s.edition,s.volume].filter(Boolean).join(' · '))}</p></div><span class="reader-location">PDF 第 ${r.page} 页</span></div><div class="reader-controls"><button id="readerPrev" aria-label="上一页">← 上一页</button><span id="readerStatus">正在加载教材…</span><label>跳转到第 <input id="readerPageInput" type="number" min="1" value="${r.page}"> 页</label><button id="readerNextHit">下一个关键词位置</button><span id="readerHitCount"></span><button id="readerNext" aria-label="下一页">下一页 →</button></div><main class="reader-stage reader-spread"><button class="reader-edge" id="readerPrevEdge" aria-label="上一页">‹</button><div class="reader-paper" id="readerPaperLeft"><canvas></canvas><span class="paper-page-number"></span></div><div class="reader-paper" id="readerPaperRight"><canvas></canvas><span class="paper-page-number"></span></div><button class="reader-edge" id="readerNextEdge" aria-label="下一页">›</button></main><div class="reader-screen-foot">键盘 ← → 或点击两侧翻页 · 页序为 PDF 页码</div></div>`;
}
function chatView() {
  const empty=state.messages.length===0;
  return `<div class="workspace-grid"><section class="chat-panel panel"><div class="panel-heading"><div><span class="section-kicker">ASK WITH EVIDENCE</span><h2>和教材一起思考</h2></div><span class="subtle-label">${icon('shield',15)} 来源可追溯</span></div>
    <div class="chat-filters"><span>回答范围</span>${filters()}</div>
    <div class="chat-body" id="chatBody">${empty?`<div class="chat-empty"><div class="empty-symbol">✳</div><span>你的教学研究伙伴</span><h3>提问，从一个知识点开始</h3><p>可询问语数英、理化生、政史地和技术教材中的问题。</p><div class="suggestions">${state.examples.map(q=>`<button data-prompt="${esc(q)}">${esc(q)} ${icon('arrow',14)}</button>`).join('')}</div><button class="refresh-examples" data-refresh-examples>${icon('arrow',14)} 换一批问题</button></div>`:state.messages.map((message,index)=>messageHTML(message,index)).join('')}${state.busy?'<div class="typing"><i></i><i></i><i></i> 正在检索教材并整理回答</div>':''}</div>
    <form id="chatForm" class="composer"><textarea id="chatInput" rows="2" maxlength="1500" placeholder="向所有学科提问…" aria-label="教学问题"></textarea><div class="composer-bottom"><span>Enter 发送 · Shift + Enter 换行</span><button type="submit" ${state.busy?'disabled':''}>发送 ${icon('send',17)}</button></div></form>
  </section></div>`;
}
function messageHTML(message,index) {
  const isUser=message.role==='user';
  let body=esc(message.content);
  if(!isUser)body=body.replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/^###? (.+)$/gm,'<strong>$1</strong>').replace(/^[-*] /gm,'• ');
  if(!isUser&&window.katex)body=body.replace(/\\\[([\s\S]*?)\\\]/g,(_,math)=>`<div class="math-block">${window.katex.renderToString(math.replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&'),{displayMode:true,throwOnError:false})}</div>`);
  body=body.replace(/\n/g,'<br>');
  if(!isUser) body=body.replace(/\[(\d+)\]/g,(_,n)=>message.citations?.some(c=>c.number===Number(n))?`<button class="cite" data-cite="${n}" data-message="${index}">[${n}]</button>`:`[${n}]`);
  return `<div class="message ${isUser?'user':'assistant'}"><div class="avatar">${isUser?icon('user',19):'<img src="/teacher.svg" alt="老师">'}</div><div class="message-main"><span class="message-name">${isUser?'你':'知页助手'}</span><div class="message-bubble">${body}</div>${!isUser&&message.notice?`<div class="answer-notice">${icon('shield',14)} ${esc(message.notice)}</div>`:''}${!isUser&&message.citations?.length?`<div class="reference-title">参考教材与定位</div><div class="message-citations">${message.citations.map(c=>`<button data-cite="${c.number}" data-message="${index}"><strong>[${c.number}] ${esc(c.title)}</strong><small>${esc([c.stage,c.subject,c.edition,c.volume,c.section?.replace(/^§\s*/,''),c.page?'PDF 第 '+c.page+' 页':'教材正文'].filter(Boolean).join(' · '))}</small>${icon('arrow',12)}</button>`).join('')}</div>`:''}</div></div>`;
}
function searchView() {
  return `<div class="search-layout"><section class="search-main"><div class="search-hero"><div class="section-kicker">TEXTBOOK SEARCH</div><h2>找到知识，也找到教材页码</h2><p>支持关键词、模糊检索与错别字建议；结果均来自已接入的教材。</p><form id="searchForm"><div class="search-box">${icon('search',21)}<input id="searchInput" value="${esc(state.searchQuery)}" placeholder="试试搜索：光合作用 / 函数 / 近代中国…" autocomplete="off"/><button type="submit">开始检索 ${icon('arrow',16)}</button></div><div class="search-suggestions" id="searchSuggestions">${suggestionHTML()}</div></form></div>
    <div class="search-controls">${filters()}</div>
    <div class="results-heading"><span>${state.searchCorrected?`未找到“${esc(state.searchQuery)}”，按“${esc(state.searchCorrected)}”显示结果`:state.searchQuery?`“${esc(state.searchQuery)}” 的结果`:'开始一次检索'}</span><small>${state.searchResults.length} 条结果</small></div>
    ${state.searchResults.length?`<div class="result-list">${state.searchResults.map(resultCard).join('')}</div>`:emptyResults()}
  </section></div>`;
}
function suggestionHTML(){
  const data=state.searchSuggestions;
  const items=data.completions.length?data.completions.slice(0,4).map(value=>({value,label:'补全'})):data.corrections.slice(0,3).map(value=>({value,label:'可能想搜'}));
  return items.length?items.map(item=>`<button type="button" data-suggest-value="${esc(item.value)}"><span>${item.label}</span>${esc(item.value)}</button>`).join(''):'';
}
function emptyResults(){return `<div class="results-empty">${icon('search',29)}<h3>这里还没有结果</h3><p>输入关键词开始检索；也可以更换学段、学科或试试短一些的关键词。</p></div>`;}
const chineseNumber = value => ({一:1,二:2,三:3,四:4,五:5,六:6,七:7,八:8,九:9,十:10})[value]||Number(value)||0;
function bookOrder(book){
  const value=`${book.volume} ${book.title}`;
  const grade=value.match(/([七八九]|[789])年级/);
  if(grade)return (chineseNumber(grade[1])-7)*10+(/上册/.test(value)?0:/下册/.test(value)?1:2);
  const type=/选择性必修|选修/.test(value)?100:/必修/.test(value)?0:200;
  const match=value.match(/(?:第\s*([一二三四五六七八九十\d]+)\s*册|([一二三四五六七八九十\d]+)册)/);
  const volume=match?chineseNumber(match[1]||match[2]):0;
  const sequence=/上/.test(value)?1:/中/.test(value)?2:/下/.test(value)?3:0;
  return type+volume*10+sequence;
}
function catalogView() {
  if(state.catalogSelection){
    const item=state.catalog.find(x=>x.id===state.catalogSelection);
    if(!item){state.catalogSelection=null;return catalogView()}
    const books=state.sources.filter(x=>x.kind==='textbook'&&x.catalog_id===item.id).sort((a,b)=>bookOrder(a)-bookOrder(b)||a.volume.localeCompare(b.volume,'zh-CN',{numeric:true}));
    return `<div class="catalog-subject"><button class="catalog-back" data-close-subject>${icon('arrow',16)} 返回教材分类</button><span class="section-kicker">${esc(item.stage)} · ${esc(item.edition)}</span><h2>${esc(item.stage)} · ${esc(item.subject)}</h2><p>已接入 ${books.length} 册，点击教材进入全屏阅读。</p><div class="book-grid">${books.map(book=>`<button class="book-item" data-read-book="${book.id}"><img class="book-cover" src="/api/sources/${book.id}/cover" alt="${esc(book.title)}封面" loading="lazy"><span><strong>${esc(book.volume||book.title)}</strong><small>${esc(book.title)}</small></span>${icon('arrow',16)}</button>`).join('')}</div>${!books.length?'<div class="results-empty"><h3>该学科暂无已接入教材</h3></div>':''}</div>`;
  }
  return `<div class="catalog-intro"><div><span class="section-kicker">ORIGINAL TEXTBOOK READER</span><h2>阅读原版教材</h2><p>先选择学段，再进入学科，查看对应的教材册次。</p></div><div class="catalog-symbol">${icon('book',33)}</div></div>${['初中','高中'].map(stage=>`<section class="stage-section"><div class="source-list-title"><h3>${stage}区</h3><span>${state.catalog.filter(x=>x.stage===stage).length} 个学科</span></div><div class="catalog-grid">${state.catalog.filter(x=>x.stage===stage).map(item=>`<button class="catalog-card subject-card" data-open-subject="${esc(item.id)}"><div class="book-glyph">${icon('book',25)}</div><h3>${esc(item.subject)}</h3><p>${esc(item.edition)}</p><div class="catalog-detail"><span>已接入 ${item.textbook_count||0} 册</span>${icon('arrow',15)}</div></button>`).join('')}</div></section>`).join('')}`;
}
let noticeTimer;
function notice(value){state.notice=value;document.querySelector('.toast')?.remove();app.insertAdjacentHTML('beforeend',`<div class="toast" role="status">${esc(value)}</div>`);clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>{state.notice='';document.querySelector('.toast')?.remove()},4200)}
async function refresh(){const [status,catalog,sources]=await Promise.all([api('/api/status'),api('/api/catalog'),api('/api/sources')]);state.status=status;state.catalog=catalog;state.sources=sources;render()}
let readerModule, readerOpenToken=0;
async function openReader(sourceId,page=1,returnView=state.view,query=''){
  const token=++readerOpenToken;
  const previous={view:returnView,scrollY:window.scrollY,bookScroll:document.querySelector('.book-list')?.scrollTop||0,
    chatScroll:document.getElementById('chatBody')?.scrollTop||0,chatDraft:document.getElementById('chatInput')?.value||''};
  try{const [data,hits]=await Promise.all([api(`/api/sources/${sourceId}/content`),query?api(`/api/sources/${sourceId}/pages?q=${encodeURIComponent(query)}`).catch(()=>({pages:[]})):Promise.resolve({pages:[]})]);if(token!==readerOpenToken)return;state.reader={...data,page:Math.max(1,page),hitPages:hits.pages};state.readerReturn=previous;state.view='reader';render();window.scrollTo(0,0);readerModule=await import('/reader.js');if(token===readerOpenToken)await readerModule.mountReader(sourceId,Math.max(1,page),hits.pages)}
  catch(error){notice(error.message)}
}
function closeReader(){
  readerOpenToken++;
  readerModule?.unmountReader();
  const previous=state.readerReturn||{view:'search',scrollY:0};
  state.reader=null;state.readerReturn=null;state.view=previous.view;render();
  requestAnimationFrame(()=>{window.scrollTo(0,previous.scrollY||0);
    const books=document.querySelector('.book-list');if(books)books.scrollTop=previous.bookScroll||0;
    const chat=document.getElementById('chatBody');if(chat)chat.scrollTop=previous.chatScroll||0;
    const draft=document.getElementById('chatInput');if(draft)draft.value=previous.chatDraft||''});
}

function bind(){
  document.querySelectorAll('[data-view]').forEach(el=>el.onclick=()=>{if(el.dataset.view==='chat')newChat();else if(el.dataset.view==='search')newSearch();else{state.view='catalog';state.notice='';render()}});
  document.querySelectorAll('[data-new-chat]').forEach(el=>el.onclick=newChat);
  document.querySelectorAll('[data-new-search]').forEach(el=>el.onclick=newSearch);
  document.querySelectorAll('[data-toggle-history]').forEach(el=>el.onclick=()=>document.querySelector('.sidebar')?.classList.toggle('history-open'));
  document.querySelectorAll('[data-chat-session]').forEach(el=>el.onclick=()=>openChatSession(el.dataset.chatSession));
  document.querySelectorAll('[data-search-session]').forEach(el=>el.onclick=()=>openSearchSession(el.dataset.searchSession));
  document.querySelectorAll('[data-refresh-examples]').forEach(el=>el.onclick=()=>{state.examples=sampleExamples(state.examples);render()});
  document.querySelectorAll('[data-prompt]').forEach(el=>el.onclick=()=>sendChat(el.dataset.prompt));
  document.querySelectorAll('[data-open-result]').forEach(el=>el.onclick=()=>{const item=state.searchResults[Number(el.dataset.openResult)];openReader(item.source_id,item.page,'search',state.searchCorrected||state.searchQuery)});
  document.querySelectorAll('[data-read-book]').forEach(el=>el.onclick=()=>openReader(Number(el.dataset.readBook),1,'catalog'));
  document.querySelectorAll('[data-close-reader]').forEach(el=>el.onclick=closeReader);
  document.querySelectorAll('[data-open-subject]').forEach(el=>el.onclick=()=>{state.catalogSelection=el.dataset.openSubject;render();window.scrollTo(0,0)});
  document.querySelectorAll('[data-close-subject]').forEach(el=>el.onclick=()=>{state.catalogSelection=null;render()});
  document.querySelectorAll('[data-cite]').forEach(el=>el.onclick=()=>{const index=Number(el.dataset.message);const citation=state.messages[index]?.citations?.find(x=>x.number===Number(el.dataset.cite));const question=[...state.messages.slice(0,index)].reverse().find(x=>x.role==='user')?.content||'';if(citation)openReader(citation.source_id,citation.page,'chat',question)});
  document.getElementById('stageFilter')?.addEventListener('change',event=>{state.stage=event.target.value;render()});
  document.getElementById('subjectFilter')?.addEventListener('change',event=>{state.subject=event.target.value;render()});
  const chatForm=document.getElementById('chatForm');if(chatForm){chatForm.onsubmit=e=>{e.preventDefault();sendChat(document.getElementById('chatInput').value)};document.getElementById('chatInput').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();chatForm.requestSubmit()}}}
  const searchForm=document.getElementById('searchForm');if(searchForm){searchForm.onsubmit=e=>{e.preventDefault();runSearch(document.getElementById('searchInput').value)};document.getElementById('searchInput').oninput=e=>queueSuggestions(e.target.value);bindSuggestionButtons()}

}
let suggestionTimer=0,suggestionSeq=0;
function bindSuggestionButtons(){document.querySelectorAll('[data-suggest-value]').forEach(el=>el.onclick=()=>runSearch(el.dataset.suggestValue))}
function queueSuggestions(query){clearTimeout(suggestionTimer);const seq=++suggestionSeq;const box=document.getElementById('searchSuggestions');if(query.trim().length<2){state.searchSuggestions={completions:[],corrections:[]};if(box)box.innerHTML='';return}suggestionTimer=setTimeout(async()=>{try{const data=await api('/api/suggest?q='+encodeURIComponent(query)+'&stage='+encodeURIComponent(state.stage)+'&subject='+encodeURIComponent(state.subject));if(seq!==suggestionSeq)return;state.searchSuggestions=data;if(box){box.innerHTML=suggestionHTML();bindSuggestionButtons()}}catch{}},220)}
async function runSearch(query){
  query=query.trim();if(query.length<2)return notice('请输入至少两个字的关键词');
  clearTimeout(suggestionTimer);suggestionSeq++;
  const id=newId(),stage=state.stage,subject=state.subject;
  const session={id,title:query.slice(0,28),query,stage,subject,results:[],corrected:'',updatedAt:Date.now()};
  state.searchSessions=[...state.searchSessions,session].slice(-10);state.activeSearchId=id;
  state.searchQuery=query;state.searchResults=[];state.searchCorrected='';state.searchSuggestions={completions:[],corrections:[]};state.busy=true;saveSessions();render();
  try{
    const data=await post('/api/search',{query,stage,subject,limit:16});
    session.results=data.results;session.corrected=data.corrected_query||'';saveSessions();
    if(state.activeSearchId===id){state.searchResults=data.results;state.searchCorrected=session.corrected;state.searchSuggestions=data.suggestions||state.searchSuggestions}
  }catch(error){notice(error.message)}finally{state.busy=false;render()}
}
async function sendChat(query){
  query=query.trim();if(query.length<2||state.busy)return;
  const history=state.messages.map(x=>({role:x.role,content:x.content})).slice(-6);
  const id=state.activeChatId||newId();
  let session=state.chatSessions.find(item=>item.id===id);
  if(!session){session={id,title:query.slice(0,28),messages:[],stage:state.stage,subject:state.subject,updatedAt:Date.now()};state.chatSessions=[...state.chatSessions,session].slice(-10)}
  const stage=state.stage,subject=state.subject;
  session.stage=stage;session.subject=subject;
  const conversation=[...state.messages,{role:'user',content:query}];
  state.activeChatId=id;state.messages=conversation;session.messages=conversation;session.updatedAt=Date.now();saveSessions();state.busy=true;render();
  try{
    const data=await post('/api/chat',{query,mode:'grounded',stage,subject,history});
    conversation.push({role:'assistant',content:data.answer,citations:data.citations,mode:data.mode,notice:data.evidence_status==='not_found'?'教材库未检索到合适内容；以下回答由模型生成，请核对。':data.interpreted_query?`已按“${data.interpreted_query}”检索教材。`:''});
  }catch(error){conversation.push({role:'assistant',content:error.message,citations:[],mode:'error'})}
  finally{
    session.messages=conversation;session.updatedAt=Date.now();
    state.chatSessions=[...state.chatSessions.filter(item=>item.id!==id),session].slice(-10);
    if(state.activeChatId===id)state.messages=conversation;
    saveSessions();state.busy=false;render();
  }
}

refresh().catch(error=>{app.innerHTML=`<div class="fatal">知识库暂时无法启动：${esc(error.message)}</div>`});
