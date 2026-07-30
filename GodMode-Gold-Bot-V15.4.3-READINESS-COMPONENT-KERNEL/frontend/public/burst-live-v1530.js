(()=>{
  const ID='gm-burst-v1530';
  const esc=(v)=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const headers=()=>{const h={Accept:'application/json'};try{const k=sessionStorage.getItem('godmode_api_key');if(k)h['X-GodMode-Key']=k}catch{}return h};
  function mount(){
    if(document.getElementById(ID))return document.getElementById(ID);
    const anchor=document.getElementById('godmode-predictor-dashboard-anchor');
    if(!anchor)return null;
    const el=document.createElement('section');el.id=ID;anchor.insertAdjacentElement('afterend',el);return el;
  }
  function metric(label,value){return `<div class="gmb-metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`}
  function render(d){
    const el=mount();if(!el)return;
    const status=String(d?.status||'STARTING').toUpperCase(),gates=Array.isArray(d?.gates)?d.gates:[];
    const passed=gates.filter(g=>g?.passed===true).length,conf=Math.round(Number(d?.confidence||0)),cont=Math.round(Number(d?.continuation||0));
    const prog=Math.round(Number(d?.beProgress?.progress||0)*100),count=Number(d?.sustained?.count||0),req=Number(d?.sustained?.required||0);
    const mode=String(d?.account?.accountTradeModeName||d?.account?.accountType||'UNKNOWN').toUpperCase();
    el.className=(status==='FIRING'||status==='FIRED')?'gmb-firing':'';
    // Rebuilding this subtree on every 1s tick reparsed unchanged markup forever and wiped any
    // text selection or focus inside the panel. renderOnce writes only when something moved.
    const html=`<div class="gmb-head"><div class="gmb-title"><i></i>Protected Burst Intelligence</div><div class="gmb-badge">${d?.enabled?'ENGINE ON':'ENGINE OFF'} · ${esc(status)}</div></div>
      <div class="gmb-grid"><div class="gmb-ring"><strong>${conf}%</strong><small>confidence</small></div><div class="gmb-metrics">
      ${metric('Deterministic BE arm',`${prog}%`)}${metric('Sustained scans',`${count}/${req||'—'}`)}${metric('Continuation',`${cont}%`)}${metric('Immediate batch',d?.batchSize?`${d.batchSize} legs`:'Waiting')}${metric('Gate trace',`${passed}/${gates.length} passed`)}${metric('Account mode',mode)}</div></div>
      <div class="gmb-blocker">${esc(d?.blocker||'Evaluating every Burst gate.')}</div><div class="gmb-gates">${gates.map(g=>`<div class="gmb-gate ${g?.passed?'gmb-pass':'gmb-fail'}"><b>${g?.passed?'✓':'×'}</b><strong>${esc(g?.name||'Gate')}</strong><small>${esc(g?.reason||'')}</small></div>`).join('')}</div>
      <div class="gmb-foot"><span>Build: ${esc(d?.buildId||'V15.4.3-READINESS-COMPONENT-KERNEL')}</span><span>Live gate trace</span></div>`;
    // The clock used to be interpolated into this string, which guaranteed the markup differed
    // on every tick and defeated any change check. It lives in its own node now.
    if(window.__godmodeRenderOnce){window.__godmodeRenderOnce(el,html)}else if(el.__gmLast!==html){el.__gmLast=html;el.innerHTML=html}
    let stamp=el.querySelector('.gmb-stamp');
    if(!stamp){stamp=document.createElement('span');stamp.className='gmb-stamp';el.querySelector('.gmb-foot')?.appendChild(stamp)}
    stamp.textContent=new Date().toLocaleTimeString();
  }
  async function poll(){
    // Shared with the React Dashboard's identical 1 Hz poll of this endpoint, so the pair costs
    // one request per second in total instead of two.
    try{const d=window.__godmodeFetchJSON
      ? await window.__godmodeFetchJSON('/api/trading-modes/protected-burst/status',700)
      : await (await fetch('/api/trading-modes/protected-burst/status',{headers:headers(),cache:'no-store',credentials:'omit'})).json();
      render(d)}
    catch(e){render({enabled:true,status:'RECONNECTING',blocker:'Burst status stream reconnecting. General backend may still be live.',gates:[],buildId:'V15.4.3-READINESS-COMPONENT-KERNEL'})}
  }
  const start=()=>{poll();setInterval(()=>{if(!document.hidden)poll()},1000)};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
