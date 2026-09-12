let sequenceCapture=null,sequenceCharacters=null,sequenceEpoch=0;
function clearSequence(){sequenceEpoch++;sequenceCapture=null;sequenceCharacters=null;const back=el('sequence-back');if(back)back.remove();modalCharacter=null}
function sequenceTargets(count,values={}){
 const c=current(),scene=byId(S.scenes,c.scene_id),people=scene.state.order.map(id=>byId(S.characters,id));
 return Array.from({length:count},(_,i)=>`<div class="sequence-target"><label>Цель ${i+1}<select name="series_target:${i}">${options(people,values['series_target:'+i],'Противник на поле')}</select></label>${input('series_external:'+i,'Название на поле',values['series_external:'+i]||'','text','maxlength="120"')}</div>`).join('');
}
function sequenceForm(a){
 const woven=a._weave?weavingCapture:null;clearSequence();const c=a._draw_character||current(),spec=a.attack_sequence;
 const count=spec.count,groups=spec.targets==='same'||spec.targets==='each'?1:count;
 modal(a.name,`<div class="entry-desc">${esc(a.description)}</div><p>${esc(spec.targets==='same'?'Все удары по одной цели':spec.targets==='each'?count+' атаки по каждому получателю':spec.targets==='different'?'Каждая атака по разной цели':'Выберите цель каждого удара')}</p>${spec.minimum?input('series_count','Количество атак',count,'number',`min="${spec.minimum}" max="${count}" required`):''}<div id="series-targets" class="fields" data-groups="${groups}">${sequenceTargets(groups)}</div>${spec.targets==='each'?btn('+ Получатель','series.add')+btn('− Получатель','series.remove','title="Убрать последнего получателя"'):''}${a.use_ready?readyFields(c,a.ready_id):''}`,async()=>{
  const f=formObject(),n=spec.minimum?Number(f.series_count):count,box=el('series-targets'),targets=Array.from({length:Number(box.dataset.groups)},(_,i)=>({target:dialogBody.querySelector('[name="series_target:'+i+'"]').value?Number(dialogBody.querySelector('[name="series_target:'+i+'"]').value):null,external_target:dialogBody.querySelector('[name="series_target:'+i+'"]').value?'':String(f['series_external:'+i]||'').trim()}));
  const attacks=spec.targets==='same'?Array.from({length:n},()=>({...targets[0]})):spec.targets==='each'?targets.flatMap(t=>Array.from({length:count},()=>({...t}))):targets;
  const root={op:'ability.use',character:c.id,ability:a.id,sequence_revision:S.revision,as_reaction:!!a.as_reaction,support_minor:!!a.support_minor,...readyPayload(a,f),...(a._draw_weapon?{draw_weapon:a._draw_weapon}:{}),...(spec.one_per_step?{steps:n}:{})};
  if(woven){root.weave_parent=woven.attack;root.targets=[...new Set(attacks.map(r=>r.target).filter(Boolean))];root.area_center_confirmed=!!f.weave_center}
  const capture={root,ability:a,plan:attacks,forms:[],index:0,characters:null};
  const epoch=sequenceEpoch,data=await sequencePreview(capture,0);if(epoch!==sequenceEpoch)return {next:()=>{}};sequenceCapture=capture;
  return {next:()=>sequenceOpen(0,data)};
 },'К броскам');if(woven&&!a.weaving_area){dialogBody.querySelectorAll('.sequence-target').forEach(row=>{const select=row.querySelector('select'),field=row.querySelector('input');select.value=String(woven.attack.targets[0]||'');select.disabled=true;if(!select.value)field.value='Цель атаки на поле'})}sequenceTargetVisibility();
}
function sequenceTargetVisibility(){dialogBody.querySelectorAll('.sequence-target').forEach(row=>{const select=row.querySelector('select'),field=row.querySelector('input');field.closest('label').hidden=!!select.value;field.required=!select.value})}
async function sequencePreview(capture,completed,plan=capture.plan){
 const response=await fetch('/api/sequence-preview/',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({...capture.root,attacks:plan,completed})});
 const data=await response.json();if(!response.ok)throw Error(data.error||'Не удалось пересчитать серию');return data;
}
function sequenceMovement(a){
 const s=a.attack_sequence,c=current(),directions=s.during_movement?['before','after']:s.one_per_step?['before']:s.step_after_attack?['after']:[];
 return directions.map(phase=>`<details class="sequence-movement" ${s.one_per_step?'open':''}><summary>${phase==='before'?'Шаг перед атакой':'Шаг после атаки'}</summary>${input('series_cells:'+phase,'Клеток',s.one_per_step?1:0,'number',`min="${s.one_per_step?1:0}" max="${s.one_per_step?1:s.step_after_attack||c.calc.speed}"`)}${input('series_cost:'+phase,'Стоимость клетки',1,'number','min="1" max="1000"')}${iceAreas(c).map(area=>input('series_ice:'+phase+':'+area.id,area.name+' · Чистые льды',0,'number','min="0"')).join('')}</details>`).join('');
}
function sequenceBackButton(){const old=el('sequence-back');if(old)old.remove();if(!sequenceCapture?.index)return;el('dialog-submit').insertAdjacentHTML('beforebegin','<button type="button" id="sequence-back" data-do="series.back">Назад</button>')}
function sequenceOpen(index,data){
 const capture=sequenceCapture;if(!capture)return;
 capture.index=index;sequenceCharacters=data.characters;
 const c=byId(data.characters,capture.root.character),a=c.abilities.find(a=>a.id===capture.root.ability),step=capture.plan[index];
 if(!a)throw Error('Умение больше недоступно');
 abilityForm({...a,_sequence:true,_draw_character:c});
 el('dialog-title').textContent=`${a.name} · ${index+1}/${capture.plan.length}`;
 dialogBody.querySelectorAll('[name="targets"]').forEach(field=>{field.checked=Number(field.value)===step.target;field.disabled=true});
 const list=dialogBody.querySelector('[name="targets"]')?.closest('.checklist');if(list){list.hidden=true;list.previousElementSibling.hidden=true}
 const roll=dialogBody.querySelector('[name=roll_result]');if(roll)roll.closest('label').firstChild.textContent=a.data.automatic_hit?'Бросок урона':'Бросок попадания и урона';
 dialogBody.insertAdjacentHTML('beforeend',sequenceMovement(a));
 dialogBody.insertAdjacentHTML('afterbegin','<div class="sequence-tools">'+btn('Пересчитать','series.refresh')+'</div>');
 updateReactionChoices();restoreSequenceFields(capture.forms[index]);updateReactionChoices();restoreSequenceFields(capture.forms[index]);updateAttackPreview();
 el('dialog-submit').textContent=index+1<capture.plan.length?'Следующий бросок':'Проверить серию';sequenceBackButton();
}
function restoreSequenceFields(fields){
 for(const old of fields||[]){const nodes=[...dialogBody.querySelectorAll('[name]')].filter(n=>n.name===old.name);for(const n of nodes){if(n.type==='checkbox'){if(n.value===old.value)n.checked=old.checked}else n.value=old.value}}
 dialogBody.querySelectorAll('select').forEach(n=>n.dispatchEvent(new Event('change',{bubbles:true})));
}
async function submitSequence(payload){
 const c=sequenceCapture,index=c.index,step=c.plan[index],f=formObject();
 const row={...step};for(const key of ['outcome','roll_result','reactions','reaction_rolls','spreads','external_bp','external_conductor','external_prone','mark_source_included','mystic_arrows','charged_arrows','charged_target','exhaustion_target','miss_damage'])if(payload[key]!==undefined)row[key]=payload[key];
 for(const phase of ['before','after']){const cells=Number(f['series_cells:'+phase]||0);delete row['movement_'+phase];if(cells)row['movement_'+phase]={cells,cell_cost:Number(f['series_cost:'+phase]||1),terrain:Object.entries(f).filter(([key,value])=>key.startsWith('series_ice:'+phase+':')&&Number(value)).map(([key,value])=>({source:Number(key.split(':')[2]),cells:Number(value)}))}}
 const plan=c.plan.map((value,i)=>i===index?row:value),data=await sequencePreview(c,index+1,plan);if(sequenceCapture!==c)return {next:()=>{}};
 c.commitKey=null;c.forms[index]=[...dialogBody.querySelectorAll('[name]')].filter(n=>n.name!=='targets').map(n=>({name:n.name,value:n.value,checked:n.checked}));c.plan=plan;
 return {next:()=>index+1<plan.length?sequenceOpen(index+1,data):sequenceReview(data)};
}
function sequenceReview(data){
 const c=sequenceCapture;c.index=c.plan.length;sequenceCharacters=data.characters;
 modal(c.ability.name+' · вся серия',`<div class="sequence-tools">${btn('Пересчитать','series.refresh')}</div><div class="log">${c.root.weave_parent?'<p><strong>Стандартная атака</strong><br>'+esc(c.root.weave_parent.roll_result)+'</p>':''}${c.plan.map((r,i)=>`<p><strong>${i+1}. ${esc(r.target?byId(data.characters,r.target).name:r.external_target)}</strong><br>${esc(r.roll_result)}${attackTargetLog(data.inputs.attack_sequence.attacks[i].inputs.attack_targets)}${(data.inputs.attack_sequence.attacks[i].movement||[]).map(m=>movementLog(m)).join('')}</p>`).join('')}</div><p class="muted">Одно применение умения. Всю серию можно отменить.</p>`,async()=>{const {weave_parent,...root}=c.root,payload={...root,attacks:c.plan};c.commitKey=c.commitKey||crypto.randomUUID();const result=await api(weave_parent?{...weave_parent,sequence_revision:root.sequence_revision,weave:payload}:payload,c.commitKey);if(sequenceCapture===c)clearSequence();return result},'Применить серию');sequenceBackButton();
}
document.addEventListener('change',e=>{if(e.target.name?.startsWith('series_target:'))sequenceTargetVisibility()});
document.addEventListener('input',e=>{if(e.target.name!=='series_count')return;const a=pendingAbility,s=a.attack_sequence;if(s.targets==='same'||s.targets==='each')return;const n=Number(e.target.value);if(!Number.isInteger(n)||n<s.minimum||n>s.count)return;const box=el('series-targets'),f=formObject();box.innerHTML=sequenceTargets(n,f);box.dataset.groups=n;sequenceTargetVisibility()});
document.addEventListener('click',async e=>{
 if(e.target.closest('[data-close]')){clearSequence();return}
 const b=e.target.closest('[data-do]');if(!b)return;
 if(['series.add','series.remove'].includes(b.dataset.do)){const box=el('series-targets'),n=Math.max(1,Number(box.dataset.groups)+(b.dataset.do==='series.add'?1:-1)),f=formObject();box.innerHTML=sequenceTargets(n,f);box.dataset.groups=n;sequenceTargetVisibility()}
 if(b.dataset.do==='series.refresh'&&sequenceCapture&&!busy){busy=true;b.disabled=true;try{const active=sequenceCapture;await refresh(true);const capture={...active,root:{...active.root,sequence_revision:S.revision}},data=await sequencePreview(capture,capture.index);if(sequenceCapture!==active)return;sequenceCapture.root=capture.root;if(capture.index===capture.plan.length)sequenceReview(data);else {sequenceCapture.forms[capture.index]=[...dialogBody.querySelectorAll('[name]')].filter(n=>n.name!=='targets').map(n=>({name:n.name,value:n.value,checked:n.checked}));sequenceOpen(capture.index,data)}}catch(error){el('dialog-error').textContent=error.message}finally{busy=false;b.disabled=false}}
 if(b.dataset.do==='series.back'&&sequenceCapture&&!busy){busy=true;b.disabled=true;try{const index=sequenceCapture.index-1,capture=sequenceCapture,data=await sequencePreview(capture,index);if(sequenceCapture===capture)sequenceOpen(index,data)}catch(error){el('dialog-error').textContent=error.message}finally{busy=false;b.disabled=false}}
});
document.addEventListener('cancel',()=>clearSequence(),true);
