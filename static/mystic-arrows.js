function mysticArrowFields(a){
 const p=a.mystic_arrows;if(!p)return '';
 return `<fieldset class="mystic-arrows"><legend>Мистическая стрела · ${p.limit===1?'один эффект':'до двух эффектов'}</legend>
 <div class="mystic-arrow-options">${p.options.map(o=>`<label><input type="checkbox" name="mystic_arrow" value="${o.id}"><span><strong>${esc(o.name)}</strong><small>${esc(o.description)}</small></span></label>`).join('')}</div>
 <small>${p.next_penalty?'После выстрела: ещё −1 к попаданию до конца боя.':'Первое применение в бою — без истощения маны.'} Промах расходует применение, но не накладывает эффекты на цель.</small></fieldset>`;
}
function mysticArrowPayload(){return {mystic_arrows:[...dialogBody.querySelectorAll('[name="mystic_arrow"]:checked')].map(x=>x.value)}}
function mysticArrowEffects(a){return (a.mystic_arrows?.options||[]).filter(o=>mysticArrowPayload().mystic_arrows.includes(o.id)&&o.effect).map(o=>({...o.effect,index:'arrow:'+o.id}))}
function updateAttackPreview(){
 const box=el('attack-preview'),a=pendingAbility;if(!box||!a)return;
 const critical=formObject().outcome==='critical';
 const bonus=[...(a.mystic_arrows?.options||[]).filter(o=>mysticArrowPayload().mystic_arrows.includes(o.id)),...selectedChargedArrows(a)].filter(o=>o.damage_contribution).map(o=>` +${o.damage_contribution.value} [${o.damage_contribution.type}]`).join('');
 box.innerHTML=`<span>База попадания <strong>${a.hit_bonus>=0?'+':''}${a.hit_bonus||0}</strong></span>${a.armored_hit_bonus!==null&&a.armored_hit_bonus!==undefined?`<span>По броне <strong>${a.armored_hit_bonus>=0?'+':''}${a.armored_hit_bonus}</strong></span>`:''}<span>${critical?'Крит':'Урон'} <strong>${esc((critical?a.critical:a.formula)+bonus)}</strong></span>${attackTargetPreview(a)}`;
}
function mysticArrowLog(value){
 if(!value)return '';
 return `<br>${esc(value.hit?value.choices.map(o=>o.description).join('; '):'Промах: эффекты стрелы не наложены.')}${(value.movements||[]).map(m=>'<br>'+esc(m.target+': сдвиг на '+m.cells+' клеток с учётом сопротивления перемещению.')).join('')}${value.external_target&&value.hit?' · цель на игровом поле':''}${value.penalty_added?'<br>Истощение маны: ещё −1 до конца боя.':''}`;
}
document.addEventListener('change',event=>{
 if(event.target.name==='outcome')updateAttackPreview();
 if(event.target.name==='targets'&&pendingAbility?.mystic_arrows&&event.target.checked){
  dialogBody.querySelectorAll('[name="targets"]').forEach(input=>{if(input!==event.target)input.checked=false});
 }
 if(event.target.name!=='mystic_arrow')return;
 const count=mysticArrowPayload().mystic_arrows.length,limit=pendingAbility?.mystic_arrows?.limit||1;
 dialogBody.querySelectorAll('[name="mystic_arrow"]').forEach(input=>{input.disabled=!input.checked&&count>=limit});
 updateAttackPreview();
 updateReactionChoices();
});
