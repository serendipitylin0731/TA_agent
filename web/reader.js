import * as pdfjs from '/vendor/pdfjs/pdf.mjs';

pdfjs.GlobalWorkerOptions.workerSrc = '/vendor/pdfjs/pdf.worker.mjs';

let active = null;

export function unmountReader() {
  if (!active) return;
  active.closed = true;
  window.removeEventListener('keydown', active.onKey);
  window.removeEventListener('resize', active.onResize);
  active.document?.destroy();
  active = null;
}

export async function mountReader(sourceId, initialPage = 1, hitPages = []) {
  unmountReader();
  const session = {sourceId, page: Math.max(1, initialPage), hitPages: [...new Set(hitPages)].sort((a,b)=>a-b), closed:false};
  active = session;
  const status = document.getElementById('readerStatus');
  try {
    const task = pdfjs.getDocument({url:`/api/sources/${sourceId}/file`, cMapUrl:'/vendor/pdfjs/cmaps/', cMapPacked:true, standardFontDataUrl:'/vendor/pdfjs/standard_fonts/'});
    session.document = await task.promise;
    if (session.closed) return;
    session.page = Math.min(session.page, session.document.numPages);
    session.onKey = event => {
      if (event.key === 'ArrowLeft') {event.preventDefault();turn(-1)}
      if (event.key === 'ArrowRight') {event.preventDefault();turn(1)}
    };
    session.onResize = () => {clearTimeout(session.resizeTimer);session.resizeTimer=setTimeout(requestDraw,150)};
    window.addEventListener('keydown', session.onKey);
    window.addEventListener('resize', session.onResize);
    document.getElementById('readerPrev').onclick=()=>turn(-1);
    document.getElementById('readerNext').onclick=()=>turn(1);
    document.getElementById('readerPrevEdge').onclick=()=>turn(-1);
    document.getElementById('readerNextEdge').onclick=()=>turn(1);
    document.getElementById('readerNextHit').onclick=()=>nextHit();
    document.getElementById('readerPageInput').onchange=event=>jump(Number(event.target.value));
    await requestDraw();
  } catch (error) {
    if (!session.closed && status) status.textContent=`教材加载失败：${error.message}`;
  }
}

function spreadStart() {
  if (!active) return 1;
  return window.matchMedia('(max-width: 720px)').matches ? active.page : Math.floor((active.page-1)/2)*2+1;
}

async function drawPage(pageNumber, slot) {
  const canvas=slot.querySelector('canvas');
  const label=slot.querySelector('.paper-page-number');
  if (!active || pageNumber > active.document.numPages) {slot.hidden=true;return}
  slot.hidden=false;
  label.textContent=`第 ${pageNumber} 页`;
  const page=await active.document.getPage(pageNumber);
  if (active.closed) return;
  const raw=page.getViewport({scale:1});
  const availableWidth=Math.max(240,slot.clientWidth-24);
  const availableHeight=Math.max(400,window.innerHeight-230);
  const scale=Math.min(availableWidth/raw.width,availableHeight/raw.height,2);
  const viewport=page.getViewport({scale});
  const pixelRatio=Math.min(window.devicePixelRatio||1,2);
  canvas.width=Math.floor(viewport.width*pixelRatio);
  canvas.height=Math.floor(viewport.height*pixelRatio);
  canvas.style.width=`${viewport.width}px`;
  canvas.style.height=`${viewport.height}px`;
  const context=canvas.getContext('2d',{alpha:false});
  await page.render({canvasContext:context,viewport,transform:[pixelRatio,0,0,pixelRatio,0,0]}).promise;
}

async function draw() {
  const session=active;
  if (!session?.document || session.closed) return;
  const start=spreadStart();
  const slots=[document.getElementById('readerPaperLeft'),document.getElementById('readerPaperRight')];
  const mobile=window.matchMedia('(max-width: 720px)').matches;
  const status=document.getElementById('readerStatus');
  const hit=document.getElementById('readerHitCount');
  const input=document.getElementById('readerPageInput');
  status.textContent=`第 ${start}${!mobile && start+1<=session.document.numPages?`–${start+1}`:''} 页 / 共 ${session.document.numPages} 页`;
  hit.textContent=session.hitPages.length?`关键词命中 ${session.hitPages.length} 页`:'当前未设置检索关键词';
  input.max=session.document.numPages;input.value=session.page;
  document.getElementById('readerPrev').disabled=start<=1;
  document.getElementById('readerNext').disabled=start+(mobile?1:2)>session.document.numPages;
  document.getElementById('readerNextHit').disabled=!session.hitPages.length;
  slots[1].hidden=mobile;
  await Promise.all([drawPage(start,slots[0]),mobile?Promise.resolve():drawPage(start+1,slots[1])]);
}

function requestDraw() {
  if (!active) return Promise.resolve();
  const session=active;
  session.drawQueue=(session.drawQueue||Promise.resolve()).catch(()=>{}).then(()=>{
    if (!session.closed) return draw();
  });
  return session.drawQueue;
}

function jump(page) {
  if (!active?.document || !Number.isFinite(page)) return;
  active.page=Math.max(1,Math.min(page,active.document.numPages));
  requestDraw();
}

function turn(direction) {if (active) jump(spreadStart()+direction*(window.matchMedia('(max-width: 720px)').matches?1:2))}

function nextHit() {
  if (!active?.hitPages.length) return;
  const visibleEnd=spreadStart()+(window.matchMedia('(max-width: 720px)').matches?0:1);
  jump(active.hitPages.find(page=>page>visibleEnd) || active.hitPages[0]);
}
