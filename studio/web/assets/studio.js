const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = {kind:'image', mode:'lazy', view:'create', filter:'all', reference:null, jobs:[], models:[], submitting:false, connected:false};
const presets = {
 portrait: 'Editorial portrait of a young woman in a white linen shirt, natural window light, subtle film grain, warm tones, candid expression, 85mm lens, shallow depth of field.',
 cinema: 'A tiny cabin beside a still alpine lake, monumental mountains, early morning mist, cinematic wide shot, soft golden light, detailed reflections, shot on 35mm film.',
 product: 'Luxury perfume bottle on a sculptural travertine pedestal, warm beige background, dramatic side lighting, delicate shadows, minimalist editorial product photography, no text.',
 dream: 'A glowing moon floating just above an endless pink desert, a tiny solitary astronaut below, lavender sky, surreal cinematic photography, soft light, vast scale.'
};
function icons(){window.lucide?.createIcons();}
function escapeHtml(value){return String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').hidden=true,5500);}
async function api(path, options={}){
 const response=await Bridge.fetch(path,options);
 const data=await response.json().catch(()=>({detail:'Réponse du moteur illisible. Réessaie.'}));
 if(!response.ok){throw new Error(typeof data.detail==='string'?data.detail:'Vérifie les valeurs saisies.');}
 return data;
}
function saveDraft(){try{localStorage.setItem('after-draft',JSON.stringify({prompt:$('#prompt').value,kind:state.kind,mode:state.mode,model:$('#model').value,steps:$('#steps').value,seed:$('#seed').value,aspect:$('#aspect').value,quality:$('#quality').value}));}catch{}}
$('#composer').addEventListener('input',saveDraft);$('#composer').addEventListener('change',saveDraft);
function selectView(view){state.view=view;$('#create-view').hidden=view!=='create';$('#gallery-view').hidden=view!=='gallery';$$('.nav').forEach(b=>{b.classList.toggle('active',b.dataset.view===view);b.setAttribute('aria-pressed',String(b.dataset.view===view));});window.scrollTo({top:0,behavior:'smooth'});}
$$('[data-view]').forEach(b=>b.addEventListener('click',()=>selectView(b.dataset.view)));
function hint(){
 const model=state.models.find(m=>m.id===$('#model').value);
 $('#mode-hint').textContent=state.kind==='video'?'Vidéo expérimentale · 2 secondes · premier essai plus long':state.mode==='lazy'?'Lazy choisit les réglages pour toi · Flux 2 Klein':`À ta main · ${model?.name || 'Choisis ton modèle'}`;
 $('#upload-button').disabled=!state.connected||state.kind!=='image'||(state.mode==='custom'&&$('#model').value!=='flux2_klein_4b');
}
function modelOptions(){
 const models=state.models.filter(m=>m.kind===state.kind);
 $('#model').innerHTML=models.map(m=>`<option value="${m.id}">${m.name} · ${m.size}</option>`).join('');
 $('#steps').value=models[0]?.steps||4;hint();
}
function setKind(kind){state.kind=kind;$$('[data-kind]').forEach(b=>{b.classList.toggle('selected',b.dataset.kind===kind);b.setAttribute('aria-pressed',String(b.dataset.kind===kind));});if(kind==='video')removeReference();modelOptions();}
$$('[data-kind]').forEach(b=>b.addEventListener('click',()=>{setKind(b.dataset.kind);saveDraft();}));
function setMode(mode){state.mode=mode;$$('[data-mode]').forEach(b=>{b.classList.toggle('selected',b.dataset.mode===mode);b.setAttribute('aria-pressed',String(b.dataset.mode===mode));});$('#custom-panel').hidden=mode!=='custom';hint();}
$$('[data-mode]').forEach(b=>b.addEventListener('click',()=>{setMode(b.dataset.mode);saveDraft();}));
$('#model').addEventListener('change',()=>{const model=state.models.find(m=>m.id===$('#model').value);$('#steps').value=model?.steps||4;if(model?.id!=='flux2_klein_4b')removeReference();hint();});
$$('[data-preset]').forEach(b=>b.addEventListener('click',()=>{$('#prompt').value=presets[b.dataset.preset];saveDraft();$('#prompt').focus();toast('L’idée est prête. Ajoute ta touche ou clique sur Créer.');}));
$('#surprise').addEventListener('click',()=>{const values=Object.values(presets);$('#prompt').value=values[Math.floor(Math.random()*values.length)];saveDraft();$('#prompt').focus();});
$('#about-open').addEventListener('click',()=>$('#about').showModal());
$$('.dialog-close').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
$$('dialog').forEach(d=>d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close();}}));
function removeReference(){state.reference=null;$('#reference-preview').hidden=true;$('#reference-preview').replaceChildren();$('#upload').value='';}
$('#upload-button').addEventListener('click',()=>$('#upload').click());
$('#upload').addEventListener('change',async()=>{
 const file=$('#upload').files[0];if(!file)return;
 const data=new FormData();data.append('file',file);$('#upload-button').disabled=true;
 try{const result=await api('/api/uploads',{method:'POST',body:data});state.reference=result.id;result.url=await Bridge.media(result.url);$('#reference-preview').innerHTML=`<img src="${result.url}" alt="Ton image de référence"><button type="button" aria-label="Retirer la référence">×</button>`;$('#reference-preview button').onclick=removeReference;$('#reference-preview').hidden=false;toast('Référence ajoutée. Décris le résultat souhaité.');}catch(e){toast(e.message);}finally{hint();}
});
$('#composer').addEventListener('submit',async e=>{
 e.preventDefault();if(state.submitting)return;if(!state.connected){Bridge.connect();return;}
 if(!$('#prompt').value.trim()){toast('Une petite description, et on y va.');$('#prompt').focus();return;}
 state.submitting=true;$('#generate').disabled=true;
 try{
  await api('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({prompt:$('#prompt').value,kind:state.kind,mode:state.mode,aspect:$('#aspect').value,quality:$('#quality').value,model:$('#model').value,steps:Number($('#steps').value),seed:Number($('#seed').value),reference:state.reference})});
  selectView('create');toast('C’est parti. Le premier essai peut télécharger le modèle.');await refresh();$('#activity').scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){toast(e.message);}finally{state.submitting=false;setBusy();}
});
document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key==='Enter'&&!$('dialog[open]')){e.preventDefault();$('#composer').requestSubmit();}});
function isActive(job){return ['starting','running','downloading'].includes(job.state);}
function setBusy(){const running=state.jobs.find(isActive);const busy=!!running;$('#generate').disabled=busy||state.submitting||!state.connected;$('#generate span').textContent=!state.connected?'Mac déconnecté':busy?'En cours':'Créer';$('#composer-connection').hidden=state.connected||Bridge.local;if(running)$('#mode-hint').textContent=running.message+(running.step?' · Étape '+running.step+' / '+(running.total||'…'):'');else hint();if(!state.connected)$('#mode-hint').textContent='La connexion au moteur est nécessaire pour créer.';}
function mediaMarkup(file,controls=false){return file.kind==='video'?`<video src="${file.url}" ${controls?'controls':'muted preload="metadata"'} playsinline></video>`:`<img src="${file.url}" alt="Création générée" loading="lazy">`;}
function resolution(job){const f=job.files?.[0];return f?.width?`${f.width}×${f.height}`:job.settings.resolution;}
function card(job){
 const media=job.files?.[0];
 const label=job.state==='failed'?'À réessayer':job.state==='cancelled'?'Arrêtée':job.message;
 return `<button class="result-card" data-job="${job.id}" aria-label="Voir la création : ${escapeHtml(job.request.prompt)}">${media?mediaMarkup(media):`<div class="job-placeholder ${job.state==='failed'?'failed':''}"><i data-lucide="${job.state==='failed'?'circle-alert':job.state==='cancelled'?'circle-stop':'loader-circle'}" ${isActive(job)?'class="spin"':''}></i><span>${escapeHtml(label)}</span></div>`}<div class="result-info"><p>${escapeHtml(job.request.prompt)}</p><small>${job.request.kind==='image'?'IMAGE':'VIDÉO'} · ${new Date(job.created*1000).toLocaleDateString('fr-FR',{day:'numeric',month:'short'})} · ${escapeHtml(resolution(job))}</small></div></button>`;
}
function renderJobs(){
 $('#gallery-count').textContent=state.jobs.filter(j=>j.state==='completed').length;
 const active=state.jobs.find(isActive);const lastFailed=!active&&state.jobs[0]?.state==='failed'?state.jobs[0]:null;$('#activity').hidden=!active&&!lastFailed;
 if(active){$('#activity').innerHTML=`<div class="activity-row"><i data-lucide="loader-circle" class="spin"></i><div><h3>${escapeHtml(active.message)}</h3><p>${active.step?`Étape ${active.step} / ${active.total||'…'}`:'Le premier lancement prend plus de temps. Tu peux continuer à explorer.'}</p></div><span id="elapsed" class="small muted"></span><button class="quiet-button" id="cancel-active">Arrêter</button></div><div class="progress-track ${active.progress==null?'indeterminate':''}"><div style="width:${active.progress??30}%"></div></div>`;$('#cancel-active').onclick=()=>cancelJob(active.id);}
 if(lastFailed){$('#activity').innerHTML=`<div class="activity-row"><i data-lucide="circle-alert"></i><div><h3>Cette création n’a pas abouti.</h3><p>${escapeHtml(lastFailed.error?.includes('noire')?'Le moteur a produit une image noire sur ce Mac. Le résultat a été écarté.':lastFailed.message)}</p></div><button class="quiet-button" id="failure-details">Voir les détails</button></div>`;$('#failure-details').onclick=()=>showJob(lastFailed.id);}
 const recent=state.jobs.slice(0,4);
 if(!recent.length){$('#recent').className='recent-empty';$('#recent').innerHTML='<div>Tout commence par une idée.<small>Ta première création apparaîtra ici.</small></div>';}if(recent.length){$('#recent').className='results-grid';$('#recent').innerHTML=recent.map(card).join('');}
 const filtered=state.jobs.filter(j=>state.filter==='all'||j.request.kind===state.filter);
 $('#gallery').innerHTML=filtered.length?filtered.map(card).join(''):'<div class="gallery-empty"><i data-lucide="sparkles"></i><h2>La prochaine idée est la bonne.</h2><p>Écris un prompt ci-dessous pour créer ta première image.</p></div>';
 $$('[data-job]').forEach(b=>b.onclick=()=>showJob(b.dataset.job));icons();setBusy();updateElapsed();
}
async function cancelJob(id){try{await api(`/api/jobs/${id}/cancel`,{method:'POST'});toast('Arrêt demandé. Le moteur libère la mémoire.');await refresh();}catch(e){toast(e.message);}}
async function reuse(job){setKind(job.request.kind);setMode(job.request.mode);$('#model').value=job.settings.model_type;$('#steps').value=job.settings.num_inference_steps;$('#seed').value=job.request.seed;$('#aspect').value=job.request.aspect;$('#quality').value=job.request.quality;$('#prompt').value=job.request.prompt;removeReference();if(job.request.reference){state.reference=job.request.reference;$('#reference-preview').innerHTML=`<img src="${await Bridge.media(`/uploads/${state.reference}.png`)}" alt="Image de référence"><button type="button" aria-label="Retirer la référence">×</button>`;$('#reference-preview button').onclick=removeReference;$('#reference-preview').hidden=false;}hint();saveDraft();$('#detail').close();selectView('create');$('#prompt').focus();}
function showJob(id){
 const job=state.jobs.find(j=>j.id===id);if(!job)return;
 $('#detail-content').innerHTML=`${(job.files||[]).map(f=>mediaMarkup(f,true)).join('')}<h3>${job.state==='completed'?'Ton idée, en vrai.':escapeHtml(job.message)}</h3><p>${escapeHtml(job.request.prompt)}</p><p>${escapeHtml(job.settings.model_type)} · ${escapeHtml(resolution(job))} · ${job.settings.num_inference_steps} étapes${job.elapsed_seconds?` · ${duration(job.elapsed_seconds)}`:""}</p>${job.error?`<details open><summary>Détails du problème</summary><pre>${escapeHtml(job.error)}</pre></details>`:''}<div class="dialog-actions"><button class="quiet-button" id="reuse"><i data-lucide="repeat-2"></i> Réutiliser le prompt</button>${(job.files||[]).map((f,i)=>`<a class="quiet-button" href="${f.url}" download="${escapeHtml(f.name||'after-creation.jpg')}"><i data-lucide="download"></i> Télécharger${i?' '+(i+1):''}</a>`).join('')}${isActive(job)?'<button class="quiet-button" id="cancel-detail">Arrêter</button>':''}<button class="text-button" id="logs">Voir le journal</button>${!isActive(job)?'<button class="text-button" id="archive-job">Retirer de la galerie</button>':''}</div><pre id="log-content" hidden></pre>`;
 $('#reuse').onclick=()=>reuse(job).catch(e=>toast(e.message));if($('#archive-job'))$('#archive-job').onclick=async()=>{try{await api(`/api/jobs/${id}`,{method:'DELETE'});$('#detail').close();await refresh();toast('Création retirée de la galerie. Le fichier reste sur ton Mac.');}catch(e){toast(e.message);}};if($('#cancel-detail'))$('#cancel-detail').onclick=()=>{cancelJob(id);$('#detail').close();};
 $('#logs').onclick=async()=>{try{const log=await api(`/api/jobs/${id}/log`);$('#log-content').textContent=log.text||'Le moteur démarre…';$('#log-content').hidden=false;}catch(e){toast(e.message);}};
 icons();$('#detail').showModal();
}
$$('[data-filter]').forEach(b=>b.addEventListener('click',()=>{state.filter=b.dataset.filter;$$('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));renderJobs();}));
let previous='', offline=false, refreshing=false;
function duration(seconds){const m=Math.floor(seconds/60),s=Math.floor(seconds%60);return m?`${m} min ${s} s`:`${s} s`;}
function updateElapsed(){const active=state.jobs.find(isActive);const target=$('#elapsed');if(active&&target)target.textContent='Depuis '+duration(Date.now()/1000-active.created);}
function connection(connected,message=''){state.connected=connected;$('#connection').textContent=connected?'Mac connecté':Bridge.paired&&!Bridge.local?'Activer le moteur':'Connecter mon Mac';$('#connect-mac').textContent=Bridge.paired&&!Bridge.local?'Activer le moteur':'Connecter mon Mac';$('#connection-dot').classList.toggle('offline',!connected);$('#connection-help').hidden=connected;if(message)$('#connection-message').textContent=message;setBusy();}
$('#connection').onclick=()=>Bridge.local?$('#about').showModal():Bridge.connect();$('#connect-mac').onclick=()=>Bridge.local?toast('Relance ./studio/start.sh depuis le dossier du projet.'):Bridge.connect();
$('#manual-connect').hidden=Bridge.local;$('#pair-manual-link').href='http://127.0.0.1:7861/?pair_origin='+encodeURIComponent(location.origin);$('#pair-code-submit').onclick=()=>{const code=$('#pair-code').value.trim();if(code.length<40||code.length>100){toast('Copie le code fourni par ton moteur local.');return;}Bridge.setToken(code);$('#pair-code').value='';};
window.addEventListener('bridge-error',e=>toast(e.detail));window.addEventListener('bridge-connected',()=>initialize());
$('#revoke-connections').hidden=!Bridge.local;$('#revoke-connections').onclick=async()=>{try{await api('/api/local/connections',{method:'DELETE'});toast('Toutes les connexions distantes ont été révoquées.');}catch(e){toast(e.message);}};
async function refresh(){
 updateElapsed();if(refreshing||!Bridge.paired)return;refreshing=true;
 try{if(!state.models.length){const config=await api('/api/config');state.models=config.models;modelOptions();}const jobs=await api('/api/jobs');for(const job of jobs)for(const file of job.files||[]){file.name=file.name||file.url.split('/').pop();file.url=await Bridge.media(file.url);}connection(true);const snapshot=JSON.stringify(jobs);if(snapshot!==previous){for(const job of jobs){const old=state.jobs.find(j=>j.id===job.id);if(old&&isActive(old)&&job.state==='completed')toast('C’est prêt ! Retrouve ta création dans la galerie.');if(old&&isActive(old)&&job.state==='failed')toast('La création a rencontré un problème. Les détails sont dans la galerie.');}state.jobs=jobs;renderJobs();previous=snapshot;}if(offline){toast('Le studio est reconnecté.');offline=false;}}
 catch(e){connection(false,e.message);if(!offline){toast(e.message);offline=true;}}finally{refreshing=false;}
}
async function initialize(){try{const config=await api('/api/config');state.models=config.models;modelOptions();try{const draft=JSON.parse(localStorage.getItem('after-draft')||'null');if(draft){setKind(draft.kind==='video'?'video':'image');setMode(draft.mode==='custom'?'custom':'lazy');for(const id of ['prompt','model','steps','seed','aspect','quality'])if(draft[id]!=null)$('#'+id).value=draft[id];hint();}}catch{}await refresh();}catch(e){connection(false,e.message);}}
$('#continue-local').onclick=()=>{$('#continue-local').href='http://127.0.0.1:7861/#prompt='+encodeURIComponent($('#prompt').value);};
async function start(){icons();$$('[data-mode],[data-kind]').forEach(b=>b.setAttribute('aria-pressed',String(b.classList.contains('selected'))));$$('.nav').forEach(b=>b.setAttribute('aria-pressed',String(b.classList.contains('active'))));connection(false);if(Bridge.paired)await initialize();if(Bridge.local){const transferred=new URLSearchParams(location.hash.slice(1)).get('prompt');if(transferred!==null){$('#prompt').value=transferred.slice(0,8000);saveDraft();history.replaceState({},'',location.pathname+location.search);}}setInterval(()=>{if(!document.hidden)refresh();},2500);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});const origin=new URLSearchParams(location.search).get('pair_origin');if(Bridge.local&&origin){$('#pair-origin').textContent=origin;$('#pair-dialog').showModal();$('#pair-reject').onclick=()=>{$('#pair-dialog').close();history.replaceState({},'', '/');};$('#pair-approve').onclick=async()=>{try{const result=await api('/api/local/pair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({origin})});if(window.opener){window.opener.postMessage({type:'after-paired',token:result.token},origin);$('#pair-result').textContent='Accès autorisé. Retourne au studio : il vérifie la connexion à ton Mac.';}else{$('#pair-result').textContent='Autorisé. Copie maintenant le code dans le studio en ligne.';$('#local-pair-code').value=result.token;$('#pair-code-output').hidden=false;$('#copy-pair-code').onclick=async()=>{try{await navigator.clipboard.writeText(result.token);$('#copy-pair-code').textContent='Copié';}catch{$('#local-pair-code').type='text';$('#local-pair-code').select();}};}$('#pair-approve').disabled=true;}catch(e){$('#pair-result').textContent=e.message;}};}}
start();
