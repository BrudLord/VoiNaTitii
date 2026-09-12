let weavingCapture=null;
function weavingField(a){return a.weaving?.ready?selector('weave_ability','Мистическое плетение',current().abilities.filter(x=>x.weavable&&x.remaining!==0).map(x=>({id:x.id,name:x.name+' · '+x.remaining+' прим.'})),null):''}
function weavingPrepare(a){modal(a.name,`<p>${esc(a.description)}</p><p>Следующая стандартная атака позволит применить магическое умение без дополнительного действия.</p>${a.use_ready?readyFields(current(),a.ready_id):''}`,async()=>api({op:'ability.use',character:current().id,ability:a.id,targets:[],as_reaction:!!a.as_reaction,...readyPayload(a,formObject())}), 'Подготовить')}
function weavingNotice(c){return c.runtime.mystic_weaving?'<p class="notice">Мистическое плетение подготовлено · следующая стандартная атака.</p>':''}
async function submitAbility(payload){
 if(weavingCapture){
  const capture=weavingCapture;
  if(payload.ability!==capture.spell.id)throw Error('Откройте стандартную атаку заново');
  payload.area_center_confirmed=!!formObject().weave_center;
  const result=await api({...capture.attack,weave:payload});weavingCapture=null;return result;
 }
 if(payload.weave_ability){
  const spell=current().abilities.find(x=>x.id===payload.weave_ability);
  if(!spell?.weavable)throw Error('Выберите магическое умение');
  return {next:()=>{
   weavingCapture={attack:payload,spell};
   abilityForm({...spell,_weave:true});
   el('dialog-submit').textContent='Применить оба';
   const names=payload.targets.length?payload.targets.map(id=>byId(S.characters,id)?.name).join(', '):'цель на игровом поле';
   const intro=document.createElement('div');intro.className='notice';
   intro.innerHTML=esc('Плетение · цель атаки: '+names+'. Дальность умения не ограничивает применение.')+(spell.weaving_area?'<label><input type="checkbox" name="weave_center" required> Получатели выбраны в области с центром на цели атаки</label>':'');
   dialogBody.prepend(intro);
   if(!spell.weaving_area)dialogBody.querySelectorAll('[name="targets"]').forEach(t=>{t.checked=payload.targets.includes(Number(t.value));t.disabled=true});
   updateReactionChoices();updateAttackPreview();
  }};
 }
 return api(payload);
}
function weavingLog(value){if(!value)return '';if(value.prepared)return '<br>Мистическое плетение подготовлено';if(!value.spell)return '<br>Плетение завершено без магического умения';const p=value.inputs||{};return '<br><strong>'+esc('Плетение · '+value.spell)+'</strong>'+(p.roll_result?'<br>Бросок: '+esc(p.roll_result):'')+attackTargetLog(p.attack_targets)+rollPoolLog(p.roll_pool)+chargedLog(p.charged_arrows)}
document.addEventListener('change',e=>{if(e.target.name==='weave_ability')el('dialog-submit').textContent=e.target.value?'Далее: заклинание':'Применить'});
