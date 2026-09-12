function heldActions(c){return [...(c.runtime.readied?[c.runtime.readied]:[]),...(c.runtime.readied_queue||[])]}
function readyFields(c,key=null){const held=heldActions(c).find(h=>!key||h.key===key);return `<section><p><strong>Условие:</strong> ${esc(held?.condition||'')}</p><label class="checks"><input type="checkbox" name="triggered" required>Условие наступило</label><h3>Проверка после действия · Ловкость 10</h3><p>Модификатор Ловкости: ${c.calc.mods.dex>=0?'+':''}${c.calc.mods.dex}</p>${input('dex_roll','Физический результат без модификатора','','number','min="-1000" max="1000" required')}<label class="checks"><input type="checkbox" name="voluntary_fail">Добровольный провал</label></section>`}
function readyPayload(a,f){return a?.use_ready?{use_ready:true,ready_id:a.ready_id,triggered:!!f.triggered,voluntary_fail:!!f.voluntary_fail,dex_roll:f.dex_roll===''?null:Number(f.dex_roll)}:{}}
function readyPanel(c,scene){if(!scene)return '';return heldActions(c).map(held=>`<details class="card" open><summary>Отложено: ${esc(actionNames[held.action])}</summary><p>${esc(held.condition)}</p><small>До конца раунда ${held.round}</small>${c.editable?`<div class="button-group">${btn('Применить умение','ready.ability',`data-ready="${esc(held.key)}"`)}${btn('Выполнить действие','ready.perform',`data-ready="${esc(held.key)}"`)}</div>`:''}</details>`).join('')+(c.editable?btn('Отложить действие','ready.reserve',` ${skippedConditions(c).length||scene.state.order[scene.state.turn]!==c.id||!c.runtime.actions?.minor?'disabled':''}`):'')}

function reserveForm(c){
 const actions=['main','move','minor'].filter(k=>(c.runtime.actions?.[k]||0)>(k==='minor'?1:0));
 modal('Отложить действие',`<p>Расходуется малое действие; выбранное действие резервируется до конца раунда.</p>${selector('ready_action','Действие',actions.map(id=>({id,name:actionNames[id]})),actions[0])}${input('ready_condition','Условие срабатывания','','text','required maxlength="500"')}`,async()=>api({op:'action.ready',character:c.id,action:formObject().ready_action,condition:formObject().ready_condition}),'Отложить');
 el('dialog-submit').disabled=!actions.length;
}
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-do]');if(!b)return;const c=current();
 if(b.dataset.do==='ready.reserve')reserveForm(c);
 if(b.dataset.do==='ready.perform')modal('Выполнить отложенное действие',readyFields(c,b.dataset.ready),async()=>api({op:'action.perform_ready',character:c.id,...readyPayload({use_ready:true,ready_id:b.dataset.ready},formObject())}),'Выполнить');
 if(b.dataset.do==='ready.ability'){
  const held=heldActions(c).find(h=>h.key===b.dataset.ready),choices=c.abilities.filter(a=>!a.ready_reason&&(a.data.category||'active')==='active'&&(a.data.action||'main')===held?.action);
  modal('Отложенное умение',selector('ready_ability','Умение',choices,null),()=>{
   const a=choices.find(a=>a.id===num(formObject().ready_ability));if(!a)throw Error('Выберите доступное умение');
   setTimeout(()=>abilityForm({...a,use_ready:true,ready_id:b.dataset.ready}),0);
  },'Продолжить');
 }
});

function shiftNotice(c){const shift=c.runtime.initiative_shift;return shift?`<p class="notice">Со следующего раунда: инициатива ${shift.value}${shift.after===c.id?'': ', после '+esc(byId(S.characters,shift.after)?.name||'участника')}.</p>`:''}

document.addEventListener('change',e=>{if(e.target.name==='voluntary_fail'){const input=dialogBody.querySelector('[name=dex_roll]');if(input){input.required=!e.target.checked;input.disabled=e.target.checked}}});
