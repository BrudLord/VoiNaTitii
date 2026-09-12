function transferPreparationForm(a){
 const c=current();
 modal(a.name,`<p>${esc(a.description)}</p><p>Подготовить истощение <strong>${a.attack_setup.strength}</strong> для следующего попадания.</p><small>${a.use_ready?'Отложенное действие':a.as_reaction?'Реакция':'Малое действие'}. Собственное истощение сохраняется; промах не расходует подготовку.</small>${c.runtime.exhaustion_transfer?'<p class="notice">Новая подготовка заменит предыдущую.</p>':''}${a.use_ready?readyFields(c,a.ready_id):''}`,async()=>api({op:'ability.use',character:c.id,ability:a.id,targets:[],as_reaction:!!a.as_reaction,...readyPayload(a,formObject())}), 'Подготовить');
}
function transferTargetFields(a){return a.attack_setup&&!a.attack_setup.prepare?`<div id="transfer-target" class="notice"></div>`:''}
function updateTransferTargets(){
 const box=el('transfer-target'),a=pendingAbility;if(!box||!a)return;
 const previous=formObject().exhaustion_target,targets=checks('targets').map(id=>byId(S.characters,id));
 const choices=a.data.system||a.data.target==='single'?targets:[...targets,{id:0,name:'Цель на игровом поле'}];
 const selected=choices.some(o=>String(o.id)===String(previous))?previous:targets.length===1?targets[0].id:null;
 box.innerHTML=`Истощение ${a.attack_setup.strength} при попадании. `+(targets.length?selector('exhaustion_target','Получатель истощения',choices,selected):'Получатель — цель на игровом поле.');
}
function transferPayload(){const value=formObject().exhaustion_target;return value?{exhaustion_target:Number(value)}:{}}
function transferNotice(c){const p=c.runtime.exhaustion_transfer;return p?`<div class="notice">Передача истощения ${p.strength} подготовлена · следующее попадание.</div>`:''}
function transferLog(value){return value?'<br>'+esc(value.prepared?'Подготовлена передача истощения '+value.strength:'Истощение '+value.strength+' → '+value.target):''}
