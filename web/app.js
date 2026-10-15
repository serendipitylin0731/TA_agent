const app = document.getElementById('app');
const SUBJECTS = ['全部学科','语文','数学','英语','物理','化学','生物学','道德与法治','思想政治','历史','地理','信息技术','通用技术'];
const state = {view:'chat',stage:'',subject:'',searchMode:'local',searchQuery:'',searchResults:[],searchSuggestions:{completions:[],corrections:[]},searchCorrected:'',webResults:[],catalog:[],sources:[],status:null,chatMode:'grounded',messages:[],busy:false,notice:'',reader:null,readerReturn:null,openUpload:false};

const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const api = async (path, options={}) => {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `请求失败 (${response.status})`);
  return data;
};
const post = (path, value) => api(path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
const icon = (name,size=19) => {
  const p={spark:'<path d="m12 2 1.9 6.1L20 10l-6.1 1.9L12 18l-1.9-6.1L4 10l6.1-1.9L12 2Z"/><path d="m19 17 .5 1.5L21 19l-1.5.5L19 21l-.5-1.5L17 19l1.5-.5L19 17Z"/>',search:'<circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4.5 4.5"/>',book:'<path d="M4 5.5c3.1-1.3 5.8-1.3 8 0v14c-2.2-1.3-4.9-1.3-8 0zM12 5.5c2.2-1.3 4.9-1.3 8 0v14c-3.1-1.3-5.8-1.3-8 0z"/>',layers:'<path d="m12 3 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 16l9 5 9-5"/>',arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',external:'<path d="M13 5h6v6M19 5l-9 9M19 14v5H5V5h5"/>',plus:'<path d="M12 5v14M5 12h14"/>',close:'<path d="M5 5l14 14M19 5 5 19"/>',send:'<path d="m3 11 18-8-8 18-2.6-7.4L3 11ZM10.4 13.6 21 3"/>',shield:'<path d="m12 2 8 3v6c0 5-3.4 8.4-8 11-4.6-2.6-8-6-8-11V5l8-3Z"/><path d="m9 12 2 2 4-4"/>',pin:'<path d="M12 21s7-5 7-12a7 7 0 1 0-14 0c0 7 7 12 7 12Z"/><circle cx="12" cy="9" r="2"/>',globe:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 4 6 4 9s-1 6-4 9M12 3c-3 3-4 6-4 9s1 6 4 9"/>',filter:'<path d="M4 6h16M7 12h10M10 18h4"/>',upload:'<path d="M12 16V4m-4 4 4-4 4 4M4 17v3h16v-3"/>',check:'<path d="m4 12 5 5L20 6"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'};
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p[name]||p.book}</svg>`;
};
const titleMap = {chat:['Chat 问答','让每个回答都能追溯到出处'],search:['查询原文','检索并在页面内阅读原始资料'],catalog:['阅读原版教材','选择教材，按 PDF 原始页序阅读'],sources:['资料管理','导入、核验与维护知识来源']};

function render() {
  if(state.view==='reader' && state.reader){app.innerHTML=readerView();bind();return}
  const title=titleMap[state.view];
  app.innerHTML=`<div class="shell">
    <aside class="sidebar"><div class="brand"><div class="brand-icon">知</div><div><strong>知页 <em>TA</em></strong><small>TEACHING ATLAS AGENT</small></div></div>
      <div class="nav-label">工作空间</div><nav aria-label="主导航">
        ${[['chat','spark','Chat 问答'],['search','search','查询原文'],['catalog','book','阅读教材']].map(([key,ic,label])=>`<button class="nav-item ${state.view===key?'active':''}" data-view="${key}">${icon(ic,18)}<span>${label}</span></button>`).join('')}
      </nav><div class="sidebar-grow"></div><div class="sidebar-card"><span class="orb">${icon('shield',18)}</span><strong>有据可查，才值得相信</strong><p>区分教材正文、公开资料与模型常识。找不到依据时，系统会明确说明。</p></div><div class="sidebar-foot"><span class="online-dot"></span> 本地知识库 <span class="version">v0.1</span></div></aside>
    <main class="main"><header class="topbar"><span>教学知识工作台 <b>/</b> ${title[0]}</span><div class="top-status"><span class="tiny-dot"></span>${state.status?.deepseek_configured?'AI 问答已就绪':'AI 问答待配置'}<button data-view="sources" title="资料管理">${icon('plus',16)}</button></div></header>
      <div class="page"><div class="heading"><div><div class="eyebrow"><span></span> EVIDENCE FIRST LEARNING <span></span></div><h1>${title[0]}<i>.</i></h1><p>${title[1]}</p></div><div class="heading-stat"><strong>${state.status?.source_count??0}</strong><span>已接入资料</span><strong>${state.status?.filled_slots??0}<small>/${state.status?.catalog_slots??20}</small></strong><span>教材目录已填充</span></div></div>
      ${state.view==='chat'?chatView():state.view==='search'?searchView():state.view==='catalog'?catalogView():sourcesView()}
      <footer class="footer"><span>知页 TA Agent · 教学研究原型</span><span>回答可能有误，请以原始资料与教师核验为准</span></footer></div>
    </main>${state.notice?`<div class="toast" role="status">${esc(state.notice)}</div>`:''}</div>`;
  bind();
}

function filters() {
  return `<div class="filters"><label>学段<select id="stageFilter"><option value="">全部学段</option><option value="初中" ${state.stage==='初中'?'selected':''}>初中</option><option value="高中" ${state.stage==='高中'?'selected':''}>高中</option></select></label><label>学科<select id="subjectFilter">${SUBJECTS.map((s,i)=>`<option value="${i?s:''}" ${state.subject===(i?s:'')?'selected':''}>${s}</option>`).join('')}</select></label></div>`;
}
function sourceBadge(kind) {return `<span class="badge ${kind}">${kind==='textbook'?'教材原件':kind==='official'?'官方资料':'开放网络资料'}</span>`;}
function locator(item) {return item.page?`PDF 第 ${item.page} 页`:(item.kind==='textbook'?'文档':'网页原文');}
function resultCard(item,index) {
  return `<article class="result-card" data-result="${index}"><div class="result-top">${sourceBadge(item.kind)}<span class="result-meta">${esc(item.stage)} · ${esc(item.subject)}</span></div><h3>${esc(item.title)}</h3><p>${esc(item.snippet)}</p><div class="result-bottom"><span>${icon('pin',14)} ${esc(item.volume||item.edition||'开放资料')} · ${locator(item)}</span><button data-open-result="${index}">在页面阅读 ${icon('arrow',14)}</button></div></article>`;
}
function readerView() {
  const r=state.reader;
  const s=r.source;
  const backLabel={chat:'Chat 问答',search:'查询原文',catalog:'阅读教材',sources:'资料管理'}[state.readerReturn?.view]||'上一页';
  return `<div class="reader-screen"><header class="reader-toolbar"><button class="reader-back" data-close-reader>${icon('arrow',17)} 返回 ${backLabel}</button><div class="reader-brand">知页 <span>· 原文阅读</span></div>${s.url?`<a class="reader-origin" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">资料来源 ${icon('external',15)}</a>`:''}</header><div class="reader-summary">${sourceBadge(s.kind)}<div><h1>${esc(s.title)}</h1><p>${esc([s.stage,s.subject,s.edition,s.volume].filter(Boolean).join(' · '))}</p></div><span class="reader-location">${s.file_type==='.pdf'?`PDF 原始页序${r.page?' · 第 '+r.page+' 页':''}`:'原文资料'}</span></div><main class="reader-stage">${s.file_type==='.pdf'?`<iframe class="reader-full-pdf" title="${esc(s.title)} PDF 阅读器" src="/api/sources/${s.id}/file${r.page?'#page='+r.page:''}"></iframe>`:`<article class="reader-document">${esc(r.text||'暂无可阅读正文')}</article>`}</main><div class="reader-screen-foot">${s.file_type==='.pdf'?'PDF 页序可能与教材印刷页码不同':`来源：${esc(s.publisher)} · ${esc(s.license)}`}</div></div>`;
}
function chatView() {
  const empty=state.messages.length===0;
  return `<div class="workspace-grid"><section class="chat-panel panel"><div class="panel-heading"><div><span class="section-kicker">ASK WITH EVIDENCE</span><h2>和知识库一起思考</h2></div><span class="subtle-label">${icon('shield',15)} 来源可追溯</span></div>
    <div class="mode-switch"><button data-chat-mode="grounded" class="${state.chatMode==='grounded'?'selected':''}">${icon('book',16)} 来源问答</button><button data-chat-mode="general" class="${state.chatMode==='general'?'selected':''}">${icon('spark',16)} 模型常识</button><span>${state.chatMode==='grounded'?'仅在找到证据时回答，附资料定位':'未核对教材，回答会明确标注'}</span></div><div class="chat-filters"><span>回答范围</span>${filters()}</div>
    <div class="chat-body" id="chatBody">${empty?`<div class="chat-empty"><div class="empty-symbol">✳</div><span>你的教学研究伙伴</span><h3>提问，从一个知识点开始</h3><p>可以问概念、比较观点、寻找出处，或让助手<br>根据现有证据梳理讲解思路。</p><div class="suggestions"><button data-prompt="光合作用的基本过程是什么？">光合作用的基本过程是什么？ ${icon('arrow',14)}</button><button data-prompt="函数的定义是什么？">函数的定义是什么？ ${icon('arrow',14)}</button><button data-prompt="近代中国社会发生了哪些变化？">近代中国社会发生了哪些变化？ ${icon('arrow',14)}</button></div></div>`:state.messages.map((message,index)=>messageHTML(message,index)).join('')}${state.busy?'<div class="typing"><i></i><i></i><i></i> 正在检索与组织证据</div>':''}</div>
    <form id="chatForm" class="composer"><textarea id="chatInput" rows="2" maxlength="1500" placeholder="输入你的教学问题…" aria-label="教学问题"></textarea><div class="composer-bottom"><span>Enter 发送 · Shift + Enter 换行</span><button type="submit" ${state.busy?'disabled':''}>发送 ${icon('send',17)}</button></div></form>
  </section><aside class="context-column"><section class="panel context-card"><div class="section-kicker">SOURCE COVERAGE</div><h2>资料覆盖</h2><div class="coverage-line"><span>教材目录</span><b>${state.status?.catalog_slots??20} 个</b></div><div class="coverage-line"><span>教材原件</span><b>${state.status?.textbook_count??0} 份</b></div><div class="coverage-line"><span>开放资料</span><b>${(state.status?.source_count??0)-(state.status?.textbook_count??0)} 份</b></div><div class="coverage-bar"><i style="width:${Math.min(100,(state.status?.filled_slots??0)/(state.status?.catalog_slots||20)*100)}%"></i></div><p>目录已建立；准确课本页码只会来自实际导入的教材文件。</p><button data-view="catalog">查看教材目录 ${icon('arrow',14)}</button></section>
    <section class="context-dark"><div class="dark-star">${icon('spark',23)}</div><h3>先找证据，再给答案</h3><p>系统会标明材料类型。开放网络资料可用于拓展，但不会被冒充成教材原文。</p><button data-view="search">探索知识库 ${icon('arrow',15)}</button></section>
    ${!state.status?.deepseek_configured?`<section class="api-tip"><strong>连接 AI 问答服务</strong><p>在项目根目录的 <code>.env</code> 中设置 API Key 并重启服务，即可启用问答。检索功能无需密钥。</p></section>`:''}
  </aside></div>`;
}
function messageHTML(message,index) {
  const isUser=message.role==='user';
  let body=esc(message.content);
  if(!isUser)body=body.replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/^###? (.+)$/gm,'<strong>$1</strong>').replace(/^[-*] /gm,'• ');
  body=body.replace(/\n/g,'<br>');
  if(!isUser) body=body.replace(/\[(\d+)\]/g,(_,n)=>message.citations?.some(c=>c.number===Number(n))?`<button class="cite" data-cite="${n}" data-message="${index}">[${n}]</button>`:`[${n}]`);
  return `<div class="message ${isUser?'user':'assistant'}"><div class="avatar">${isUser?'我':'知'}</div><div class="message-main"><span class="message-name">${isUser?'你':'知页助手'}${!isUser?` · ${message.mode==='general'?'模型常识':'来源问答'}`:''}</span><div class="message-bubble">${body}</div>${!isUser&&message.citations?.length?`<div class="reference-title">参考资料与定位</div><div class="message-citations">${message.citations.map(c=>`<button data-cite="${c.number}" data-message="${index}"><strong>[${c.number}] ${esc(c.title)}</strong><small>${esc([c.stage,c.subject,c.edition,c.volume].filter(Boolean).join(' · '))} · ${c.page?'PDF 第 '+c.page+' 页':'网页原文'}</small>${icon('arrow',12)}</button>`).join('')}</div>`:''}</div></div>`;
}
function searchView() {
  const local=state.searchMode==='local';
  return `<div class="search-layout"><section class="search-main"><div class="search-hero"><div class="section-kicker">KNOWLEDGE DISCOVERY</div><h2>找到知识，也找到出处</h2><p>支持关键词、模糊检索与错别字建议；只有教材原件才会显示 PDF 页码。</p><form id="searchForm"><div class="search-box">${icon('search',21)}<input id="searchInput" value="${esc(state.searchQuery)}" placeholder="试试搜索：光合作用 / 函数 / 近代中国…" autocomplete="off"/><button type="submit">开始检索 ${icon('arrow',16)}</button></div><div class="search-suggestions" id="searchSuggestions">${suggestionHTML()}</div></form></div>
    <div class="search-controls"><div class="tabs"><button data-search-mode="local" class="${local?'selected':''}">本地知识库</button><button data-search-mode="web" class="${!local?'selected':''}">联网开放资料</button></div>${local?filters():`<span class="web-note">中文维基百科 · CC BY-SA 4.0 · 导入后才参与问答</span>`}</div>
    <div class="results-heading"><span>${state.searchCorrected?`未找到“${esc(state.searchQuery)}”，按“${esc(state.searchCorrected)}”显示结果`:state.searchQuery?`“${esc(state.searchQuery)}” 的结果`:'开始一次检索'}</span><small>${local?state.searchResults.length:state.webResults.length} 条结果</small></div>
    ${local?(state.searchResults.length?`<div class="result-list">${state.searchResults.map(resultCard).join('')}</div>`:emptyResults()):(state.webResults.length?`<div class="result-list">${state.webResults.map((item,i)=>`<article class="result-card web"><div class="result-top">${sourceBadge('open_web')}<span class="result-meta">中文维基百科</span></div><h3>${esc(item.title)}</h3><p>${esc(item.snippet)}</p><div class="result-bottom"><a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">来源网页 ${icon('external',14)}</a><button data-import-web="${i}">${icon('plus',14)} 导入并阅读</button></div></article>`).join('')}</div>`:emptyResults())}
  </section></div>`;
}
function suggestionHTML(){
  const data=state.searchSuggestions;
  const items=data.completions.length?data.completions.slice(0,4).map(value=>({value,label:'补全'})):data.corrections.slice(0,3).map(value=>({value,label:'可能想搜'}));
  return items.length?items.map(item=>`<button type="button" data-suggest-value="${esc(item.value)}"><span>${item.label}</span>${esc(item.value)}</button>`).join(''):'';
}
function emptyResults(){return `<div class="results-empty">${icon('search',29)}<h3>这里还没有结果</h3><p>输入关键词开始检索。若教材内容尚未导入，可试试联网开放资料。</p></div>`;}
function catalogView() {
  const items=state.catalog.filter(item=>(!state.stage||item.stage===state.stage)&&(!state.subject||item.subject===state.subject));
  const books=state.sources.filter(source=>source.kind==='textbook'&&(!state.stage||source.stage===state.stage)&&(!state.subject||source.subject===state.subject));
  return `<div class="catalog-intro"><div><span class="section-kicker">ORIGINAL TEXTBOOK READER</span><h2>在这里阅读已接入的原版教材</h2><p>有原件的教材会显示在阅读列表，点击后直接打开 PDF。当前目录记录版本信息；未接入正文的教材不会显示虚构页码。</p><div class="official-links"><a href="https://basic.smartedu.cn/" target="_blank" rel="noopener noreferrer">国家中小学智慧教育平台 ${icon('external',13)}</a><a href="https://www.pep.com.cn/szkjxzy/dzjc/ywjy/" target="_blank" rel="noopener noreferrer">人教社官方电子教材 ${icon('external',13)}</a></div></div><div class="catalog-symbol">${icon('book',33)}</div></div><div class="catalog-toolbar">${filters()}<button class="light-button" data-view="sources">${icon('upload',16)} 导入教材</button></div><div class="textbook-layout"><div><div class="source-list-title"><h3>可阅读教材</h3><span>${books.length} 份</span></div>${books.length?`<div class="book-list">${books.map(book=>`<button class="book-item" data-read-book="${book.id}">${icon('book',21)}<span><strong>${esc(book.title)}</strong><small>${esc(book.stage)} · ${esc(book.subject)} · ${esc(book.volume)} · ${book.chunk_count?book.chunk_count+' 个检索片段':'仅可阅读'}</small></span>${icon('arrow',15)}</button>`).join('')}</div>`:`<div class="results-empty">${icon('book',27)}<h3>尚未取得可展示的教材原件</h3><p>可导入有使用权限的 PDF；原版阅读器会保留文件原始页序。</p></div>`}<div class="source-list-title"><h3>教材版本目录</h3><span>${items.length} 项</span></div><div class="catalog-grid">${items.map(item=>`<article class="catalog-card"><div class="catalog-card-top"><span>${esc(item.stage)}</span><span class="catalog-state ${item.textbook_count?'ready':''}">${item.textbook_count?'已有原件':'待接入'}</span></div><div class="book-glyph">${icon('book',25)}</div><h3>${esc(item.subject)}</h3><p>${esc(item.edition)}</p><div class="catalog-detail"><span>已接入原件</span><b>${item.textbook_count||0} 份</b></div><div class="catalog-links"><a href="${esc(item.catalog_url)}" target="_blank" rel="noopener noreferrer">官方版本信息 ${icon('external',13)}</a><button data-upload-catalog="${esc(item.id)}">导入 ${icon('arrow',13)}</button></div></article>`).join('')}</div><div class="catalog-note">${icon('shield',17)} 统编版适用语文、历史和道德与法治/思想政治。其他学科目前按人教版或浙江省用书目录建档。</div></div></div>`;
}
function sourcesView() {
  return `<div class="source-layout"><section class="source-main"><div class="source-head"><div><span class="section-kicker">KNOWLEDGE LIBRARY</span><h2>让资料有清晰的来处</h2><p>管理教材原件与可开放复用的网络资料。每份材料都标记类型、版本和定位方式。</p></div><button class="primary-button" data-action="toggle-upload">${icon('plus',16)} 导入资料</button></div>
  ${state.openUpload?`<form id="uploadForm" class="upload-form"><div class="upload-title"><strong>导入有使用权限的教材文件</strong><button type="button" data-action="toggle-upload" aria-label="关闭">${icon('close',16)}</button></div><div class="upload-fields"><label>教材目录<select name="catalog_id" required>${state.catalog.map(item=>`<option value="${esc(item.id)}">${esc(item.stage)} · ${esc(item.subject)} · ${esc(item.edition)}</option>`).join('')}</select></label><label>具体册次<input name="volume" placeholder="例如：七年级上册 / 必修第一册" maxlength="70" required></label></div><label class="file-drop">${icon('upload',22)}<span>选择 PDF、TXT 或 Markdown 文件</span><small>PDF 保留页码；单份不超过 35 MB。扫描件需先 OCR。</small><input name="file" type="file" accept=".pdf,.txt,.md" required></label><label class="auth-check"><input name="authorized" type="checkbox" required> 我确认有权在本地项目中处理此文件，且不会未经许可公开教材全文。</label><button class="primary-button" type="submit">开始解析与索引 ${icon('arrow',16)}</button></form>`:''}
  <div class="source-list-title"><h3>已入库资料</h3><span>${state.sources.length} 份</span></div>${state.sources.length?`<div class="source-list">${state.sources.map(source=>`<div class="source-item"><span class="source-icon ${source.kind}">${icon(source.kind==='textbook'?'book':'globe',20)}</span><div><strong>${esc(source.title)}</strong><small>${esc(source.stage)} · ${esc(source.subject)} · ${esc(source.edition||'开放资料')} · ${source.chunk_count} 个片段</small><em>${esc(source.license)}</em></div><div class="source-actions"><button data-open-source="${source.id}" title="在阅读界面查看原文">${icon('external',16)}</button><button data-delete-source="${source.id}" title="从知识库删除">${icon('close',16)}</button></div></div>`).join('')}</div>`:`<div class="results-empty">${icon('layers',28)}<h3>还没有索引资料</h3><p>可先到知识检索页查找开放资料并导入。</p></div>`}</section><aside class="source-aside"><div class="panel rules-card"><span class="section-kicker">SOURCE POLICY</span><h3>资料进入知识库的规则</h3><ul><li>教材文件由有权限的使用者在本地导入。</li><li>网上资料必须保留原文链接与许可信息。</li><li>模型不能把开放网页说成教材原文。</li><li>教材页码仅指导入 PDF 的实际页序。</li></ul><a href="/about.html" target="_blank">阅读来源与边界说明 ${icon('arrow',14)}</a></div></aside></div>`;
}

let noticeTimer;
function notice(value){state.notice=value;document.querySelector('.toast')?.remove();app.insertAdjacentHTML('beforeend',`<div class="toast" role="status">${esc(value)}</div>`);clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>{state.notice='';document.querySelector('.toast')?.remove()},4200)}
async function refresh(){const [status,catalog,sources]=await Promise.all([api('/api/status'),api('/api/catalog'),api('/api/sources')]);state.status=status;state.catalog=catalog;state.sources=sources;render()}
async function openReader(sourceId,page=0,returnView=state.view){
  const previous={view:returnView,scrollY:window.scrollY,bookScroll:document.querySelector('.book-list')?.scrollTop||0,
    chatScroll:document.getElementById('chatBody')?.scrollTop||0,chatDraft:document.getElementById('chatInput')?.value||''};
  try{const data=await api(`/api/sources/${sourceId}/content`);state.reader={...data,page};state.readerReturn=previous;state.view='reader';render();window.scrollTo(0,0)}
  catch(error){notice(error.message)}
}
function closeReader(){
  const previous=state.readerReturn||{view:'search',scrollY:0};
  state.reader=null;state.readerReturn=null;state.view=previous.view;render();
  requestAnimationFrame(()=>{window.scrollTo(0,previous.scrollY||0);
    const books=document.querySelector('.book-list');if(books)books.scrollTop=previous.bookScroll||0;
    const chat=document.getElementById('chatBody');if(chat)chat.scrollTop=previous.chatScroll||0;
    const draft=document.getElementById('chatInput');if(draft)draft.value=previous.chatDraft||''});
}

function bind(){
  document.querySelectorAll('[data-view]').forEach(el=>el.onclick=()=>{state.view=el.dataset.view;state.notice='';render()});
  document.querySelectorAll('[data-chat-mode]').forEach(el=>el.onclick=()=>{state.chatMode=el.dataset.chatMode;render()});
  document.querySelectorAll('[data-search-mode]').forEach(el=>el.onclick=()=>{state.searchMode=el.dataset.searchMode;render()});
  document.querySelectorAll('[data-prompt]').forEach(el=>el.onclick=()=>sendChat(el.dataset.prompt));
  document.querySelectorAll('[data-upload-catalog]').forEach(el=>el.onclick=()=>{state.view='sources';state.openUpload=true;render();document.querySelector('[name="catalog_id"]').value=el.dataset.uploadCatalog});
  document.querySelectorAll('[data-action="toggle-upload"]').forEach(el=>el.onclick=()=>{state.openUpload=!state.openUpload;render()});
  document.querySelectorAll('[data-open-result]').forEach(el=>el.onclick=()=>{const item=state.searchResults[Number(el.dataset.openResult)];openReader(item.source_id,item.page,'search')});
  document.querySelectorAll('[data-read-book]').forEach(el=>el.onclick=()=>openReader(Number(el.dataset.readBook),0,'catalog'));
  document.querySelectorAll('[data-open-source]').forEach(el=>el.onclick=()=>openReader(Number(el.dataset.openSource),0,'sources'));
  document.querySelectorAll('[data-close-reader]').forEach(el=>el.onclick=closeReader);
  document.querySelectorAll('[data-import-web]').forEach(el=>el.onclick=async()=>{const item=state.webResults[Number(el.dataset.importWeb)];try{const imported=await post('/api/web/import',{pageid:item.pageid,subject:state.subject||'通用'});await refresh();await openReader(imported.source_id,0,'search');notice(`已导入“${item.title}”，保留原文与许可信息`)}catch(error){notice(error.message)}});
  document.querySelectorAll('[data-delete-source]').forEach(el=>el.onclick=async()=>{if(!window.confirm('确认从本地知识库删除这份资料？'))return;try{await api(`/api/sources/${el.dataset.deleteSource}`,{method:'DELETE'});await refresh();notice('资料已删除')}catch(error){notice(error.message)}});
  document.querySelectorAll('[data-cite]').forEach(el=>el.onclick=()=>{const citation=state.messages[Number(el.dataset.message)]?.citations?.find(x=>x.number===Number(el.dataset.cite));if(citation)openReader(citation.source_id,citation.page,'chat')});
  document.getElementById('stageFilter')?.addEventListener('change',event=>{state.stage=event.target.value;render()});
  document.getElementById('subjectFilter')?.addEventListener('change',event=>{state.subject=event.target.value;render()});
  const chatForm=document.getElementById('chatForm');if(chatForm){chatForm.onsubmit=e=>{e.preventDefault();sendChat(document.getElementById('chatInput').value)};document.getElementById('chatInput').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();chatForm.requestSubmit()}}}
  const searchForm=document.getElementById('searchForm');if(searchForm){searchForm.onsubmit=e=>{e.preventDefault();runSearch(document.getElementById('searchInput').value)};document.getElementById('searchInput').oninput=e=>queueSuggestions(e.target.value);bindSuggestionButtons()}
  const uploadForm=document.getElementById('uploadForm');if(uploadForm)uploadForm.onsubmit=async e=>{e.preventDefault();const button=uploadForm.querySelector('button[type="submit"]');button.disabled=true;try{const data=await api('/api/upload',{method:'POST',body:new FormData(uploadForm)});state.openUpload=false;await refresh();await openReader(data.source_id,0,'catalog');notice(`已索引 ${data.chunks} 个片段${data.pages?'，共 '+data.pages+' 页':''}`)}catch(error){button.disabled=false;notice(error.message)}};
}
let suggestionTimer=0,suggestionSeq=0;
function bindSuggestionButtons(){document.querySelectorAll('[data-suggest-value]').forEach(el=>el.onclick=()=>runSearch(el.dataset.suggestValue))}
function queueSuggestions(query){clearTimeout(suggestionTimer);const seq=++suggestionSeq;const box=document.getElementById('searchSuggestions');if(query.trim().length<2){state.searchSuggestions={completions:[],corrections:[]};if(box)box.innerHTML='';return}suggestionTimer=setTimeout(async()=>{try{const data=await api('/api/suggest?q='+encodeURIComponent(query)+'&stage='+encodeURIComponent(state.stage)+'&subject='+encodeURIComponent(state.subject));if(seq!==suggestionSeq)return;state.searchSuggestions=data;if(box){box.innerHTML=suggestionHTML();bindSuggestionButtons()}}catch{}},220)}
async function runSearch(query){query=query.trim();if(query.length<2)return notice('请输入至少两个字的关键词');clearTimeout(suggestionTimer);suggestionSeq++;state.searchQuery=query;state.searchCorrected='';state.searchSuggestions={completions:[],corrections:[]};state.busy=true;render();try{if(state.searchMode==='local'){const data=await post('/api/search',{query,stage:state.stage,subject:state.subject,limit:16});state.searchResults=data.results;state.searchCorrected=data.corrected_query||'';state.searchSuggestions=data.suggestions||state.searchSuggestions}else{const data=await api('/api/web/search?q='+encodeURIComponent(query));state.webResults=data.results}}catch(error){notice(error.message)}finally{state.busy=false;render()}}
async function sendChat(query){query=query.trim();if(query.length<2||state.busy)return;const history=state.messages.map(x=>({role:x.role,content:x.content})).slice(-6);state.messages.push({role:'user',content:query});state.busy=true;render();const body=document.getElementById('chatBody');body?.scrollTo({top:body.scrollHeight});try{const data=await post('/api/chat',{query,mode:state.chatMode,stage:state.stage,subject:state.subject,history});state.messages.push({role:'assistant',content:data.answer,citations:data.citations,mode:state.chatMode})}catch(error){state.messages.push({role:'assistant',content:error.message,citations:[],mode:state.chatMode})}finally{state.busy=false;render();const updated=document.getElementById('chatBody');updated?.scrollTo({top:updated.scrollHeight})}}

refresh().catch(error=>{app.innerHTML=`<div class="fatal">知识库暂时无法启动：${esc(error.message)}</div>`});
