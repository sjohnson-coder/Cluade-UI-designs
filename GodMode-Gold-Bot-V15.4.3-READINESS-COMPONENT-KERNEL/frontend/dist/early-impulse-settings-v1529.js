(() => {
  'use strict';
  const CARD_ID = 'godmode-early-impulse-settings';
  const API = window.location.origin;
  const BUILD = 'V15.4.3-READINESS-COMPONENT-KERNEL';
  const intentFields = [
    ['earlyIntentEnabled','Enable Early Intent','toggle'],
    ['earlyIntentPriorityLoopSeconds','Priority Scan Interval (sec)','number',0.15,2,0.05],
    ['earlyIntentWindowSeconds','Intent Tick Window (sec)','number',2,12,0.5],
    ['earlyIntentMinTicks','Intent Minimum Ticks','number',6,100,1],
    ['earlyIntentHardMinTicks','Intent Hard Minimum Ticks','number',5,50,1],
    ['earlyIntentProbability','Intent Probability (%)','percent',55,95,1],
    ['earlyIntentMinDisplacementAtr','Minimum Intent Move ATR','number',0.03,0.30,0.01],
    ['earlyIntentVelocityAtrPerSecond','Intent Velocity','number',0.005,0.10,0.001],
    ['earlyIntentAccelerationAtrPerSecond','Intent Acceleration','number',0.003,0.10,0.001],
    ['earlyIntentPrebreakBufferAtr','Pre-break Buffer ATR','number',0,0.30,0.01],
    ['earlyIntentMaxExtensionAtr','Max Intent Extension ATR','number',0.15,1.0,0.01],
    ['earlyIntentMaxReversalPenalty','Max Reversal Penalty','number',0,1,0.01],
    ['earlyIntentProbeLotMultiplier','Intent Probe Lot Multiplier','number',0.10,0.50,0.05],
    ['earlyIntentContextGateEnabled','Context Quality Gate','toggle'],
    ['earlyIntentContextRequireM15Support','Require M15 Support','toggle'],
    ['earlyIntentContextMinScore','Minimum Context Score (%)','percent',40,90,1],
    ['earlyIntentContextMaxLegMoveAtr','Maximum Fresh Leg ATR','number',0.25,3,0.05],
    ['earlyIntentContextMaxRunBars','Maximum Directional Run Bars','number',3,20,1],
    ['earlyIntentContextTerminalSwingPosition','Terminal Swing Edge (%)','percent',2,40,1],
    ['earlyIntentContextMaxExtensionAtr','Maximum Context Extension ATR','number',0.10,2,0.05],
    ['earlyIntentProbeRiskPct','Probe Risk (% equity)','number',0.01,1,0.01],
    ['earlyIntentProbeMinStopPoints','Probe Minimum Stop Points','number',0.10,10,0.10],
    ['earlyIntentProbeMaxStopPoints','Probe Maximum Stop Points','number',0.25,15,0.10],
    ['earlyIntentProbeStopAtr','Probe Stop ATR','number',0.10,2,0.05],
    ['earlyIntentProbePromotionProfitR','Promotion Profit R','number',0.05,1.5,0.05],
    ['earlyIntentProbeStallSeconds','Probe Stall Timeout (sec)','number',5,180,5],
    ['earlyIntentProbeFastFailR','Probe Fast-Fail R','number',-1,-0.05,0.05],
    ['earlyIntentProbeBreakevenR','Probe Break-even R','number',0.05,1.5,0.05],
    ['earlyIntentProbeTrailStartR','Probe Trail Start R','number',0.10,2,0.05],
    ['earlyIntentProbeTrailAtr','Probe Trail ATR','number',0.10,1.5,0.05],
  ];
  const impulseFields = [
    ['earlyImpulsePredictorEnabled','Enable Predictor','toggle'],
    ['earlyImpulseLiveCandleAnalysis','Live Forming Candle','toggle'],
    ['earlyImpulseDynamicThresholds','Dynamic Thresholds','toggle'],
    ['earlyImpulseProgressiveExecution','Progressive Execution','toggle'],
    ['earlyIntentTriggerCandleCacheSeconds','M5 Context Refresh (sec)','number',0.25,5,0.05],
    ['earlyIntentContextCandleCacheSeconds','M15 Context Refresh (sec)','number',1,30,0.5],
    ['fastSniperLoopSeconds','General Scan Interval (sec)','number',0.25,5,0.05],
    ['earlyImpulseWindowSeconds','Impulse Tick Window (sec)','number',4,60,1],
    ['earlyImpulseMinTicks','Minimum Tick Sample','number',6,200,1],
    ['earlyImpulseVelocityAtrPerSecond','Velocity Threshold','number',0.001,0.2,0.001],
    ['earlyImpulseAccelerationAtrPerSecond','Acceleration Threshold','number',0.001,0.2,0.001],
    ['earlyImpulseCompressionRatio','Compression Ratio','number',0.2,1.2,0.01],
    ['earlyImpulseBodyAtr','Live Body Threshold ATR','number',0.05,2,0.01],
    ['earlyImpulseSpreadExpansionMultiple','Spread Expansion Limit','number',1,5,0.05],
    ['earlyImpulseProbeProbability','Probe Probability (%)','percent',50,99,1],
    ['earlyImpulseConfirmProbability','Confirm Probability (%)','percent',50,99,1],
    ['earlyImpulseMinProbeAtr','Minimum Probe Move ATR','number',0.03,2,0.01],
    ['earlyImpulseMinConfirmAtr','Minimum Confirm Move ATR','number',0.05,3,0.01],
    ['earlyImpulseMaxExtensionAtr','Maximum Entry Extension ATR','number',0.15,3,0.01],
    ['earlyImpulseMaxSweepPenalty','Maximum Sweep Penalty','number',0,1,0.01],
    ['earlyImpulseProbeLotMultiplier','Probe Lot Multiplier','number',0.1,1,0.05],
    ['earlyImpulseStopAtr','Impulse Stop ATR','number',0.3,3,0.05],
  ];
  let settings = null;
  let revision = 0;
  let pollTimer = 0;

  const key = () => { try { return sessionStorage.getItem('godmode_api_key') || ''; } catch { return ''; } };
  const headers = () => ({'Content-Type':'application/json', ...(key()?{'X-GodMode-Key':key()}:{})});
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pct = v => Math.max(0, Math.min(100, Number(v || 0) * 100));
  const persistent = value => {
    const out = JSON.parse(JSON.stringify(value || {}));
    ['mt5','source','stale','staleReason','settingsRevision','serverBuildId','recoveryState','secretConfigured'].forEach(k => delete out[k]);
    if(out.telegram && typeof out.telegram === 'object') delete out.telegram.botTokenConfigured;
    return out;
  };
  async function getJson(path) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 2500);
    try {
      const r = await fetch(API + path, {headers:headers(), cache:'no-store', credentials:'omit', signal:controller.signal});
      const body = await r.json().catch(()=>({}));
      if(!r.ok) throw new Error(body.message || `Predictor status HTTP ${r.status}`);
      return body;
    } finally { window.clearTimeout(timer); }
  }
  async function loadSettings() {
    const s = await getJson('/api/settings');
    if(!s || s.ok === false || !s.serverBuildId) throw new Error(s?.message || 'Verified settings unavailable');
    settings = s;
    revision = Number(s.settingsRevision || s.meta?.settingsRevision || 0);
    return s;
  }
  function inputHtml([name,label,type,min,max,step]) {
    const value = settings?.automation?.[name];
    if(type === 'toggle') return `<label class="form-row eip-row"><span>${esc(label)}</span><button type="button" class="toggle ${value !== false ? 'on':''}" data-eip-toggle="${name}" aria-pressed="${value !== false}"></button></label>`;
    const shown = type === 'percent' ? Math.round(Number(value ?? 0) * 100) : Number(value ?? 0);
    return `<label class="form-row eip-row"><span>${esc(label)}</span><input class="input form-input" type="number" data-eip-input="${name}" data-eip-type="${type}" value="${esc(shown)}" min="${min}" max="${max}" step="${step}"></label>`;
  }
  function cardHtml() {
    const enabled = settings?.automation?.earlyImpulsePredictorEnabled !== false;
    return `<div id="${CARD_ID}" class="card early-impulse-card span-full">
      <div class="section-title"><h3 class="card-title"><span class="eip-bolt">ϟ</span>4. Early Impulse Predictor</h3><div class="button-wrap"><span class="tag ${enabled?'green':'red'}" id="eip-engine-tag">${enabled?'Engine ON':'Engine OFF'}</span><span class="tag blue" id="eip-stage-tag">STARTING</span></div></div>
      <div class="early-impulse-layout">
        <div class="early-impulse-controls"><div class="settings-subhead">Early Intent probe layer</div>${intentFields.map(inputHtml).join('')}</div>
        <div class="early-impulse-controls"><div class="settings-subhead">Two-stage anticipatory entry</div>${impulseFields.map(inputHtml).join('')}<div class="impulse-safety-note"><span>✓</span><div><strong>Execution safety remains authoritative</strong><span>News, spread, extension, liquidity-sweep, stop-loss, broker admission, risk and live-certification gates cannot be bypassed here.</span></div></div></div>
        <div class="early-impulse-diagnostics">
          <div class="impulse-live-head"><div><span class="eyebrow">EARLY INTENT / IMPULSE</span><strong id="eip-side-stage">— · STARTING</strong></div><div class="impulse-probability"><span id="eip-probability">0%</span><small>probability</small></div></div>
          <div id="eip-error" class="impulse-offline" hidden></div>
          <div class="impulse-stage-track"><span data-stage="WATCH">WATCH</span><span data-stage="PROBE">PROBE</span><span data-stage="CONFIRMED">CONFIRMED</span></div>
          <div class="impulse-meter-list">${[['Velocity','velocity_score'],['Acceleration','acceleration_score'],['Persistence','directional_score'],['Compression release','compression_release_score'],['Spread quality','spread_score'],['Live candle','candle_score']].map(([l,k])=>`<div class="impulse-meter"><div><span>${l}</span><strong id="eip-${k}-value">0%</strong></div><div class="progress-track"><div id="eip-${k}-bar" class="progress-fill" style="width:0%"></div></div></div>`).join('')}</div>
          <div class="impulse-diagnostic-grid"><div><span>Move</span><strong id="eip-move">0.00 ATR</strong></div><div><span>Sweep risk</span><strong id="eip-sweep">0%</strong></div><div><span>Context</span><strong id="eip-context">—</strong></div><div><span>Lifecycle</span><strong id="eip-lifecycle">WATCH</strong></div><div><span>Priority loop</span><strong id="eip-loop">0.25s</strong></div><div><span>MT5</span><strong id="eip-mt5">OFFLINE</strong></div><div><span>Tick age</span><strong id="eip-tick-age">—</strong></div><div><span>Endpoint</span><strong id="eip-fetch-latency">—</strong></div></div>
          <div class="impulse-priority-state"><div><span>Priority execution</span><strong id="eip-priority-state">STARTING</strong></div><p id="eip-priority-reason">Waiting for the first priority scan.</p></div>
          <p class="tiny muted impulse-reason" id="eip-reason">Waiting for live predictor state.</p>
          <button type="button" class="outline-button impulse-refresh" id="eip-refresh">↻ Refresh diagnostics</button>
        </div>
      </div>
      <div class="eip-footer"><p class="tiny muted"><strong>Build:</strong> ${BUILD}. Status polling is read-only and never runs a trade decision.</p><div class="button-wrap"><button type="button" class="ghost-button" id="eip-reload">Reload Predictor</button><button type="button" class="gold-button" id="eip-save">Save Predictor Settings</button></div></div>
      <div id="eip-message" class="eip-message" hidden></div>
    </div>`;
  }
  function showMessage(text, bad=false) {
    const el=document.getElementById('eip-message'); if(!el)return;
    el.hidden=false; el.textContent=text; el.className=`eip-message ${bad?'negative':'positive'}`;
    setTimeout(()=>{if(el)el.hidden=true},5000);
  }
  function bind() {
    document.querySelectorAll('[data-eip-toggle]').forEach(el => el.addEventListener('click', () => {
      const name=el.dataset.eipToggle; const on=!el.classList.contains('on'); el.classList.toggle('on',on); el.setAttribute('aria-pressed',String(on));
      settings.automation[name]=on;
      if(name==='earlyImpulsePredictorEnabled'){const tag=document.getElementById('eip-engine-tag');tag.textContent=on?'Engine ON':'Engine OFF';tag.className=`tag ${on?'green':'red'}`;}
    }));
    document.querySelectorAll('[data-eip-input]').forEach(el => el.addEventListener('change', () => {
      let v=Number(el.value); if(!Number.isFinite(v))return; if(el.dataset.eipType==='percent')v/=100; settings.automation[el.dataset.eipInput]=v;
    }));
    document.getElementById('eip-save')?.addEventListener('click', save);
    document.getElementById('eip-reload')?.addEventListener('click', async()=>{try{await loadSettings(); render(true);showMessage('Verified predictor settings reloaded.')}catch(e){showMessage(e.message,true)}});
    document.getElementById('eip-refresh')?.addEventListener('click', ()=>poll(true));
  }
  async function save() {
    const btn=document.getElementById('eip-save'); if(btn)btn.disabled=true;
    try {
      const r=await fetch(API+'/api/settings',{method:'POST',headers:headers(),credentials:'omit',body:JSON.stringify({settings:persistent(settings),expectedRevision:revision})});
      const data=await r.json().catch(()=>({}));
      if(!r.ok || data.ok!==true) throw new Error(data.message || 'Save failed; previous verified configuration remains active.');
      settings=data.settings; revision=Number(data.revision || data.settings?.settingsRevision || revision+1);
      showMessage(`Early Impulse Predictor saved and verified. Revision ${revision}.`);
    } catch(e) { showMessage(e.message || 'Save failed.', true); try{await loadSettings();render(true)}catch{} }
    finally {if(btn)btn.disabled=false;}
  }
  function updateDiagnostics(data) {
    const intent=data?.earlyIntent || {};
    const impulse=data?.earlyImpulse || {};
    const chosen = Number(intent.probability||0) >= Number(impulse.probability||0) ? intent : impulse;
    const stage=String(chosen.runtimeStatus || chosen.stage || data?.endpointStatus || 'STARTING').toUpperCase();
    const side=String(chosen.side || '—').toUpperCase();
    const prob=pct(chosen.probability);
    const stageTag=document.getElementById('eip-stage-tag');
    if(stageTag){stageTag.textContent=stage;stageTag.className=`tag ${stage==='CONFIRMED'?'green':stage==='PROBE'||stage==='INTENT'?'gold':['WATCH','COLLECTING','STARTING','LIVE'].includes(stage)?'blue':'red'}`;}
    const set=(id,text)=>{const el=document.getElementById(id);if(el)el.textContent=text};
    set('eip-side-stage',`${side} · ${stage}`); set('eip-probability',`${prob.toFixed(0)}%`);
    document.querySelectorAll('.impulse-stage-track [data-stage]').forEach(el=>el.classList.toggle('active',el.dataset.stage===stage));
    ['velocity_score','acceleration_score','directional_score','compression_release_score','spread_score','candle_score'].forEach(k=>{const v=pct(chosen[k]);set(`eip-${k}-value`,`${v.toFixed(0)}%`);const bar=document.getElementById(`eip-${k}-bar`);if(bar)bar.style.width=`${v}%`;});
    const priority=data?.priorityIntent||{}; const health=priority.health||{};
    const priorityState=String(priority.runtimeStatus||health.runtimeStatus||data?.endpointStatus||'STARTING').toUpperCase();
    const lastExec=priority.lastExecution||{}; const blocker=priority.lastBlocker||lastExec.message||'';
    const priorityReason=priorityState==='ORDER_SENT' ? `Order dispatch ${Number(lastExec.dispatchLatencyMs||0).toFixed(0)}ms; end-to-end ${Number(lastExec.endToEndSinceFirstSeenMs||0).toFixed(0)}ms.` : (blocker || priority.lastDecision?.reason || `Loop health: ${String(health.status||'starting')}.`);
    const context=chosen.context||{}; const contextLabel=context.allowed===false?'BLOCKED':context.allowed===true?`${pct(context.score).toFixed(0)}% OK`:'—';
    set('eip-move',`${Number(chosen.displacement_atr||0).toFixed(2)} ATR`); set('eip-sweep',`${pct(chosen.sweep_penalty||chosen.reversal_penalty).toFixed(0)}%`); set('eip-context',contextLabel); set('eip-lifecycle',stage); set('eip-loop',`${Number(health.expectedIntervalSeconds||settings?.automation?.earlyIntentPriorityLoopSeconds||0.25).toFixed(2)}s`); set('eip-mt5', data?.mt5?.connected?'LIVE':'OFFLINE');
    set('eip-tick-age',chosen.latestTickAgeMs==null?'—':`${Number(chosen.latestTickAgeMs).toFixed(0)}ms`); set('eip-fetch-latency',`${Number(data?.endpointLatencyMs||0).toFixed(1)}ms`); set('eip-priority-state',priorityState); set('eip-priority-reason',priorityReason);
    const tickInfo=Number.isFinite(Number(chosen.tickCount))?` Ticks: ${Number(chosen.tickCount)}${chosen.latestTickAgeMs!=null?` · age ${Number(chosen.latestTickAgeMs)}ms`:''}.`:'';
    set('eip-reason',(chosen.reason || 'Waiting for enough live ticks to calculate the next predictor state.')+tickInfo);
    const er=document.getElementById('eip-error'); if(er)er.hidden=true;
  }
  async function poll(manual=false) {
    if(document.hidden || !document.getElementById(CARD_ID))return;
    try{const data=await getJson('/api/fast-sniper/status');updateDiagnostics(data);if(manual)showMessage(`Predictor endpoint ${Number(data.endpointLatencyMs||0).toFixed(1)}ms.`);}
    catch(e){const er=document.getElementById('eip-error');if(er){er.hidden=false;er.textContent=`Predictor status endpoint unavailable. General backend health is checked separately. ${e.message||''}`;}if(manual)showMessage(e.message||'Predictor diagnostics refresh failed.',true);}
  }
  async function render(force=false) {
    if(!location.hash.includes('settings'))return;
    const grid=document.querySelector('.settings-grid'); if(!grid)return;
    const nativeCard=[...document.querySelectorAll('.early-impulse-card')].find(el=>el.id!==CARD_ID);
    if(nativeCard) nativeCard.remove();
    if(document.getElementById(CARD_ID) && !force)return;
    if(!settings)await loadSettings();
    document.getElementById(CARD_ID)?.remove();
    const cards=grid.querySelectorAll(':scope > .card'); const anchor=cards[4] || null;
    const holder=document.createElement('div');holder.innerHTML=cardHtml();grid.insertBefore(holder.firstElementChild,anchor);bind();void poll();
  }
  function scheduleRender(){setTimeout(()=>render().catch(e=>console.warn('[Early Impulse UI]',e)),250)}
  window.addEventListener('hashchange',scheduleRender);
  const observer=new MutationObserver(()=>{if(location.hash.includes('settings')&&!document.getElementById(CARD_ID))scheduleRender()});
  observer.observe(document.documentElement,{childList:true,subtree:true});
  scheduleRender();
  pollTimer=window.setInterval(()=>void poll(),2000);
  window.__godmodeLegacyPredictorPollStop=()=>window.clearInterval(pollTimer);
  window.addEventListener('beforeunload',()=>window.clearInterval(pollTimer));
})();
