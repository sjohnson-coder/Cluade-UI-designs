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
    el.innerHTML=`<div class="gmb-head"><div class="gmb-title"><i></i>Protected Burst Intelligence</div><div class="gmb-badge">${d?.enabled?'ENGINE ON':'ENGINE OFF'} · ${esc(status)}</div></div>
      <div class="gmb-grid"><div class="gmb-ring"><strong>${conf}%</strong><small>confidence</small></div><div class="gmb-metrics">
      ${metric('Deterministic BE arm',`${prog}%`)}${metric('Sustained scans',`${count}/${req||'—'}`)}${metric('Continuation',`${cont}%`)}${metric('Immediate batch',d?.batchSize?`${d.batchSize} legs`:'Waiting')}${metric('Gate trace',`${passed}/${gates.length} passed`)}${metric('Account mode',mode)}</div></div>
      <div class="gmb-blocker">${esc(d?.blocker||'Evaluating every Burst gate.')}</div><div class="gmb-gates">${gates.map(g=>`<div class="gmb-gate ${g?.passed?'gmb-pass':'gmb-fail'}"><b>${g?.passed?'✓':'×'}</b><strong>${esc(g?.name||'Gate')}</strong><small>${esc(g?.reason||'')}</small></div>`).join('')}</div>
      <div class="gmb-foot"><span>Build: ${esc(d?.buildId||'V15.4.3-READINESS-COMPONENT-KERNEL')}</span><span>Live gate trace · ${new Date().toLocaleTimeString()}</span></div>`;
  }
  async function poll(){
    try{const r=await fetch('/api/trading-modes/protected-burst/status',{headers:headers(),cache:'no-store',credentials:'omit'});const d=await r.json();render(d)}
    catch(e){render({enabled:true,status:'RECONNECTING',blocker:'Burst status stream reconnecting. General backend may still be live.',gates:[],buildId:'V15.4.3-READINESS-COMPONENT-KERNEL'})}
  }
  const start=()=>{poll();setInterval(()=>{if(!document.hidden)poll()},1000)};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
