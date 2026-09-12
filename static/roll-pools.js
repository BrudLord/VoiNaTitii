function rollPoolForm(a){
 const c=current(),scene=byId(S.scenes,c.scene_id),spec=a.roll_pool,people=scene.state.order.map(id=>byId(S.characters,id));
 modal(a.name,`<p class="description">${esc(a.description)}</p>${a.use_ready?readyFields(c,a.ready_id):''}<h3>Физические броски</h3><div class="dice-inputs ${spec.parity?'assigned-dice':''}">${Array.from({length:spec.dice},(_,i)=>`<div>${input('die'+i,'К'+(i+1),'','number',`min="1" max="${spec.sides}" required`)}${spec.parity?selector('die_target'+i,'Получатель',people,null):''}</div>`).join('')}</div><div class="pool-totals" id="pool-totals" aria-live="polite">Введите все кубики</div><h3>Распределение</h3><div class="allocation-list">${people.map(t=>`<article class="card"><div class="card-title"><strong>${esc(t.name)}</strong><small>${t.runtime.hp}/${t.calc.max_hp} ХП</small></div>${spec.parity?'<p id="allocated-'+t.id+'">Лечение: 0</p>':input('heal'+t.id,'Лечение',0,'number','min="0" required')}${spec.cleanse_cost?(t.runtime.effects||[]).filter(e=>e.duration!=='aura').map(e=>`<label class="checks"><input type="checkbox" name="cleanse${t.id}" value="${esc(e.key)}">Снять ${esc(e.name)} · ${spec.cleanse_cost}</label>`).join(''):''}</article>`).join('')}</div><p class="muted">Лечение по кубикам появится у мастера для внесения ХП. Урон противникам он учитывает отдельно.</p>`,async()=>{
  const f=formObject(),dice=Array.from({length:spec.dice},(_,i)=>Number(f['die'+i]));
  const allocations=people.map(t=>({character:t.id,hp:Number(f['heal'+t.id]),remove:[...dialogBody.querySelectorAll(`[name="cleanse${t.id}"]:checked`)].map(e=>e.value)}));
  await api({op:'ability.use',character:c.id,ability:a.id,as_reaction:!!a.as_reaction,...readyPayload(a,f),outcome:'hit',dice,allocations,dice_targets:spec.parity?dice.map((v,i)=>v%2&&f['die_target'+i]?Number(f['die_target'+i]):null):undefined});
 },'Применить');
 const update=()=>{
  const f=formObject(),dice=Array.from({length:spec.dice},(_,i)=>Number(f['die'+i]));
  if(spec.parity)dice.forEach((v,i)=>{dialogBody.querySelector('[name=die_target'+i+']').closest('label').hidden=!(Number.isInteger(v)&&v>=1&&v<=spec.sides&&v%2)});
  const complete=dice.every(v=>Number.isInteger(v)&&v>=1&&v<=spec.sides);
  const heal=dice.filter(v=>!spec.parity||v%2).reduce((a,b)=>a+b,0),damage=spec.parity?dice.filter(v=>v%2===0).reduce((a,b)=>a+b,0):0;
  const assigned=Object.fromEntries(people.map(t=>[t.id,dice.reduce((sum,v,i)=>sum+(v%2&&num(f['die_target'+i])===t.id?v:0),0)]));
  if(spec.parity)for(const t of people)el('allocated-'+t.id).textContent='Лечение: '+assigned[t.id];
  const spent=spec.parity?Object.values(assigned).reduce((a,b)=>a+b,0):people.reduce((sum,t)=>sum+num(f['heal'+t.id])+dialogBody.querySelectorAll(`[name="cleanse${t.id}"]:checked`).length*(spec.cleanse_cost||0),0);
  el('pool-totals').textContent=complete?`Лечение: ${heal} · Распределено: ${spent} · Осталось: ${heal-spent}${spec.parity?' · Урон Светом: '+damage:''}`:'Введите все кубики';
  el('dialog-submit').disabled=!complete||spent>heal;
 };
 for(const box of dialogBody.querySelectorAll('.dice-inputs,.allocation-list')){box.addEventListener('input',update);box.addEventListener('change',update)}
 update();
}
function pendingHealing(){
 const rows=S.characters.flatMap(c=>Object.entries(c.runtime.pending_heals||{}).map(([key,p])=>({c,key,p})));
 return rows.length?`<section><h2>Лечение по броскам</h2>${rows.map(({c,key,p})=>`<article class="card"><h3>${esc(p.name)} · ${esc(c.name)}</h3><p>Кубики: ${p.dice.join(', ')}</p>${p.allocations.map(r=>`<p>${esc(byId(S.characters,r.character)?.name)}: +${r.hp} ХП</p>`).join('')}${btn('Внести лечение','healing.confirm',`data-character="${c.id}" data-pending="${esc(key)}"`)}${btn('Уже учтено вручную','healing.dismiss',`data-character="${c.id}" data-pending="${esc(key)}"`)}</article>`).join('')}</section>`:'';
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-do="healing.confirm"],[data-do="healing.dismiss"]');if(!b)return;
 try{await command({op:b.dataset.do,character:num(b.dataset.character),pending:b.dataset.pending})}catch(err){toast(err.message)}
});
function rollPoolLog(pool){return pool?`<br>Запас лечения: ${pool.healing_pool} · Осталось: ${pool.unused}${pool.damage_pool?' · Урон Светом противникам: '+pool.damage_pool:''}${pool.allocations.map(r=>'<br>'+esc(byId(S.characters,r.character)?.name)+': лечение '+r.hp+(r.remove.length?', снятие эффектов: '+r.remove.length:'')).join('')}`:''}
