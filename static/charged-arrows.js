function chargedPreparationForm(a){
 const c=current();
 modal(a.name,`<p>${esc(a.description)}</p><p>Следующее умение 1 круга или выше расходует подготовку, в том числе при промахе. Число эффектов определяется Ор в формуле до крита.</p>${a.use_ready?readyFields(c,a.ready_id):''}`,async()=>submitAbility({op:'ability.use',character:c.id,ability:a.id,targets:[],...readyPayload(a,formObject())}),'Подготовить');
}
function chargedArrowFields(a){
 const p=a.charged_arrows;if(!p||p.prepare)return '';
 if(!p.limit)return '<p class="notice">Это умение расходует Заряженные стрелы, но в его уроне нет Ор: дополнительные эффекты не появятся.</p>';
 return `<fieldset class="charged-arrows"><legend>Заряженные стрелы · до ${p.limit} эффектов</legend>${Array.from({length:p.limit},(_,i)=>selector('charged_slot_'+i,'Эффект '+(i+1),p.options.map(o=>({id:o.id,name:o.name+' · '+o.description})),null)).join('')}<div id="charged-target"></div><small>Можно пропустить эффекты. Подготовка расходуется при применении, даже при промахе.</small></fieldset>`;
}
function chargedArrowPayload(){
 const f=formObject(),p=pendingAbility?.charged_arrows;
 return {charged_arrows:Array.from({length:p?.limit||0},(_,i)=>f['charged_slot_'+i]).filter(Boolean),...(f.charged_target!==undefined&&f.charged_target!==''?{charged_target:Number(f.charged_target)}:{})};
}
function selectedChargedArrows(a){const p=chargedArrowPayload();return p.charged_arrows.map((k,i)=>({...a.charged_arrows.options.find(o=>o.id===k),id:'charged:'+i+':'+k}))}
function updateChargedTarget(){
 const box=el('charged-target'),a=pendingAbility;if(!box||!a)return;
 const previous=formObject().charged_target,targets=checks('targets').map(id=>byId(S.characters,id));
 const choices=a.data.system||a.data.target==='single'?targets:[...targets,{id:0,name:'Цель на игровом поле'}];
 const selected=choices.some(o=>String(o.id)===String(previous))?previous:targets.length===1?targets[0].id:null;
 box.innerHTML=targets.length?selector('charged_target','Получатель эффектов',choices,selected):'<small>Получатель — цель на игровом поле.</small>';
}
function chargedArrowEffects(a,id){
 const selected=chargedArrowPayload().charged_target;
 return Number(selected)===Number(id)?selectedChargedArrows(a).filter(o=>o.effect).map(o=>({...o.effect,index:'arrow:'+o.id})):[];
}
function chargedNotice(c){return c.runtime.charged_arrows?'<div class="notice">Заряженные стрелы подготовлены · следующее умение 1 круга или выше.</div>':''}
function chargedLog(value){return !value?'':value.prepared?'<br>Заряженные стрелы подготовлены.':value.skipped?'<br>Подготовка Заряженных стрел израсходована без дополнительных эффектов.':mysticArrowLog(value)}
document.addEventListener('change',event=>{
 if(event.target.name?.startsWith('charged_')){updateReactionChoices();updateAttackPreview()}
});
