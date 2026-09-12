function targetOutcome(id){const f=formObject();return f['target-outcome:'+String(id||0)]||f.outcome||'hit'}
function targetOutcomesPayload(){const fields=[...dialogBody.querySelectorAll('[name^="target-outcome:"]')];return fields.length?{target_outcomes:Object.fromEntries(fields.map(field=>[field.name.split(':')[1],field.value||formObject().outcome||'hit']))}:{}}
function updateTargetOutcomes(){
 const box=el('target-outcomes');if(!box)return;const ids=checks('targets'),previous=formObject();
 box.innerHTML=ids.length<2?'':'<h3 class="form-section">Исходы по целям</h3><div class="fields">'+ids.map(id=>selector('target-outcome:'+id,byId(S.characters,id)?.name||'Цель',[{id:'hit',name:pendingAbility.data.automatic_hit?'Автопопадание':'Попадание'},...(pendingAbility.data.automatic_hit?[]:[{id:'miss',name:'Промах'}]),{id:'critical',name:'Крит'}],previous['target-outcome:'+id]||'')).join('')+'</div>';
 box.querySelectorAll('select').forEach(select=>{select.options[0].textContent='Общий исход'});
}
function marks(c){return (c.calc.effects||[]).filter(e=>(e.status||e.name)==='Метка')}
function markSourceField(c,a){return !a.data.automatic_hit&&(a.data.damage||a.data.weapon)&&marks(c).some(e=>!e.source_id)?'<label><input type="checkbox" name="mark_source_included"> Атака включает источник метки на поле</label>':''}
function markPenalty(){const ids=checks('targets');return marks(current()).some(e=>e.source_id?!ids.includes(e.source_id):!formObject().mark_source_included)?-3:0}
function externalTargetField(a){return a.data.damage||a.data.weapon?'<div id="external-bp"></div>':''}
function updateExternalTarget(){
 const box=el('external-bp');if(!box)return;
 const old=formObject().external_bp||0,prone=!!formObject().external_prone,conductor=formObject().external_conductor||0;
 box.innerHTML=checks('targets').length?'':(!pendingAbility?.data.automatic_hit||pendingAbility?.data.damage_from_bp?input('external_bp','БП противника на поле',old,'number','min="0" max="1000" step="1"'):'')+(pendingAbility?.physical_weapon_units?input('external_conductor','Сверхпроводник на противнике',conductor,'number','min="0" max="1000" step="1"'):'')+(pendingAbility?.data.automatic_hit?'':`<label><input type="checkbox" name="external_prone" ${prone?'checked':''}> Противник сбит с ног</label>`);
}
function scopedTargetEffects(a,target){
 const base=w=>String(w).replace(/\s+\d+(?:\s+в\s+\d+)?$/,'').trim();
 return (target.calc.effects||[]).filter(e=>(!e.ability_scope||e.ability_scope===a.hit_scope)&&(!e.keyword||(a.data.keywords||[]).some(w=>base(w)===base(e.keyword))));
}
function targetAdvantage(a,target){return Math.max(0,...scopedTargetEffects(a,target).filter(e=>['БП','Шок'].includes(reactionStatus(e))).map(e=>e.value))}
function targetHitBonus(a,target){return targetAdvantage(a,target)+scopedTargetEffects(a,target).filter(e=>e.stat==='target_hit'&&!['БП','Шок'].includes(reactionStatus(e))).reduce((n,e)=>n+e.value,0)}
function targetDamageFormula(a,target){
 const critical=targetOutcome(target?.id)==='critical';
 let result=critical?a.critical:a.formula;
 const bp=target?targetAdvantage(a,target):Number(formObject().external_bp||0);
 const strength=target?Math.max(0,...(target.calc.effects||[]).filter(e=>(e.status||e.name)==='Сверхпроводник').map(e=>Math.abs(e.value))):Number(formObject().external_conductor||0);
 const conductor=strength*(a.physical_weapon_units||0)/2;
 if(conductor)result+=' +'+conductor+' [Сверхпроводник]';
 if(a.data.damage_from_bp&&bp)result+=' +'+bp+' [БП]';
 if(targetOutcome(target?.id)==='miss')return a.data.miss_damage_divisor?'('+result+') / '+a.data.miss_damage_divisor:'0';
 const choices=(a.mystic_arrows?.options||[]).filter(o=>mysticArrowPayload().mystic_arrows.includes(o.id));
 if((target?.id||0)===Number(chargedArrowPayload().charged_target||0))choices.push(...selectedChargedArrows(a));
 for(const o of choices)if(o.damage_contribution)result+=' +'+o.damage_contribution.value+' ['+o.damage_contribution.type+']';
 return result;
}
function attackTargetPreview(a){
 const ids=checks('targets'),sign=n=>(n>=0?'+':'')+n;
 return (ids.length?ids.map(id=>byId(S.characters,id)):[null]).map(t=>{
 const bonus=t?targetHitBonus(a,t):Number(formObject().external_bp||0)+(formObject().external_prone&&(a.data.keywords||[]).some(w=>/^Ближний(?:\s|$)/.test(w))?2:0),penalty=markPenalty(),total=a.hit_bonus+bonus+penalty;
 if(targetOutcome(t?.id)==='miss')return `<div>${esc(t?t.name:'Цель на игровом поле')}: <strong>промах</strong><br>Формула <strong>${esc(targetDamageFormula(a,t))}</strong>${missDamageField(a,t)}</div>`;
 if(a.data.automatic_hit)return `<div>${esc(t?t.name:'Цель на игровом поле')}: <strong>автоматическое попадание</strong><br>Формула <strong>${esc(targetDamageFormula(a,t))}</strong>${missDamageField(a,t)}${forcedMovementPreview(a,t)}</div>`;
 return `<div>${(a.roll_conditions||[]).length?'<strong>'+esc(a.roll_conditions.join(' · '))+'</strong><br>':''}${esc(t?t.name:'Цель на игровом поле')}: попадание <strong>${sign(total)}</strong>${penalty?' (метка −3)':''}${bonus?' (бонус цели '+sign(bonus)+')':''}${a.armored_hit_bonus!=null?' · по броне '+sign(a.armored_hit_bonus+bonus+penalty):''}<br>Формула <strong>${esc(targetDamageFormula(a,t))}</strong>${missDamageField(a,t)}${forcedMovementPreview(a,t)}</div>`;
 }).join('');
}
function attackTargetLog(rows){return (rows||[]).map(r=>'<br>'+esc(r.name+(r.outcome==='miss'?': промах':r.outcome==='critical'?': крит':r.automatic_hit?': автоматическое попадание':': попадание '+(r.hit>=0?'+':'')+r.hit)+(r.mark_penalty?' · метка '+r.mark_penalty:'')+(r.target_bonus?' · бонус цели '+r.target_bonus:'')+(r.armored_hit!=null?' · по броне '+r.armored_hit:'')+(r.damage?' · формула '+r.damage:'')+(r.miss_damage?' · урон '+r.miss_damage.incoming+' ÷ '+r.miss_damage.divisor+' = '+r.miss_damage.remaining.toLocaleString('ru'):'')+(r.roll_conditions?.length?' · '+r.roll_conditions.join(' · '):''))).join('')}
document.addEventListener('input',e=>{if(['external_bp','external_prone','external_conductor','mark_source_included'].includes(e.target.name))updateAttackPreview()});

function forcedMovementPreview(a,target){
 if(!target||targetOutcome(target.id)==='miss')return '';
 const choices=(a.mystic_arrows?.options||[]).filter(o=>mysticArrowPayload().mystic_arrows.includes(o.id));
 if(target.id===Number(chargedArrowPayload().charged_target||0))choices.push(...selectedChargedArrows(a));
 let blocked=[...(target.calc.effects||[]),...(a.data.effects||[]).filter(e=>!e.manual)].some(e=>(e.status||e.name)==='Обездвижен');const lines=[];
 for(const o of choices){if(o.movement)lines.push(blocked?'Сдвиг невозможен: Обездвижен':'Сдвиг '+Math.max(0,o.movement-(target.calc.forced_movement_reduction||0))+' клеток');if((o.effect?.status||o.effect?.name)==='Обездвижен')blocked=true}
 return lines.length?'<br>'+lines.map(esc).join(' · '):'';
}

function missDamagePayload(){return Object.fromEntries([...dialogBody.querySelectorAll('[name^="miss-damage:"]')].map(n=>[n.name.split(':')[1],n.value===''?null:Number(n.value)]))}
function missDamageField(a,target){if(targetOutcome(target?.id)!=='miss'||!a.data.miss_damage_divisor)return '';const key=String(target?.id||0),value=formObject()['miss-damage:'+key]??'';return input('miss-damage:'+key,'Урон до деления · '+(target?.name||'цель на поле'),value,'number','min="0" max="100000" step="any" required')+`<small data-miss-total="${key}" data-divisor="${a.data.miss_damage_divisor}">${value===''?'Введите итог броска урона со всеми бонусами':'После деления: '+(Number(value)/a.data.miss_damage_divisor).toLocaleString('ru')}. ХП вносит мастер.</small>`}
document.addEventListener('input',e=>{if(!e.target.name.startsWith('miss-damage:'))return;const key=e.target.name.split(':')[1],box=dialogBody.querySelector('[data-miss-total="'+key+'"]');if(box)box.textContent=e.target.value===''?'Введите итог броска урона со всеми бонусами':'После деления: '+(Number(e.target.value)/Number(box.dataset.divisor)).toLocaleString('ru')+'. ХП вносит мастер.'});

document.addEventListener('change',e=>{if(e.target.name?.startsWith('target-outcome:'))updateReactionChoices()});
