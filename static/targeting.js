function externalTargetField(a){return a.data.damage||a.data.weapon?'<div id="external-bp"></div>':''}
function updateExternalTarget(){
 const box=el('external-bp');if(!box)return;
 const old=formObject().external_bp||0;
 box.innerHTML=checks('targets').length?'':input('external_bp','БП противника на поле',old,'number','min="0" max="1000" step="1"');
}
function targetHitBonus(a,target){
 const base=w=>String(w).replace(/\s+\d+(?:\s+в\s+\d+)?$/,'').trim();
 const scope=a.hit_scope;
 return (target.calc.effects||[]).filter(e=>e.stat==='target_hit'&&(!e.ability_scope||e.ability_scope===scope)&&(!e.keyword||(a.data.keywords||[]).some(w=>base(w)===base(e.keyword)))).reduce((n,e)=>n+e.value,0);
}
function targetDamageFormula(a,target){
 const critical=formObject().outcome==='critical';
 let result=critical?a.critical:a.formula;
 const bp=target?Math.max(0,...(target.calc.effects||[]).filter(e=>(e.status||e.name)==='БП'&&e.stat==='target_hit').map(e=>e.value)):Number(formObject().external_bp||0);
 if(a.data.damage_from_bp&&bp)result+=' +'+bp+' [БП]';
 if(formObject().outcome==='miss')return result;
 const choices=(a.mystic_arrows?.options||[]).filter(o=>mysticArrowPayload().mystic_arrows.includes(o.id));
 if((target?.id||0)===Number(chargedArrowPayload().charged_target||0))choices.push(...selectedChargedArrows(a));
 for(const o of choices)if(o.damage_contribution)result+=' +'+o.damage_contribution.value+' ['+o.damage_contribution.type+']';
 return result;
}
function attackTargetPreview(a){
 const ids=checks('targets'),sign=n=>(n>=0?'+':'')+n;
 return (ids.length?ids.map(id=>byId(S.characters,id)):[null]).map(t=>{
 const bonus=t?targetHitBonus(a,t):Number(formObject().external_bp||0),total=a.hit_bonus+bonus;
 return `<div>${esc(t?t.name:'Цель на игровом поле')}: попадание <strong>${sign(total)}</strong>${bonus?' (бонус цели '+sign(bonus)+')':''}${a.armored_hit_bonus!=null?' · по броне '+sign(a.armored_hit_bonus+bonus):''}<br>Формула <strong>${esc(targetDamageFormula(a,t))}</strong></div>`;
 }).join('');
}
function attackTargetLog(rows){return (rows||[]).map(r=>'<br>'+esc(r.name+': попадание '+(r.hit>=0?'+':'')+r.hit+(r.target_bonus?' · бонус цели '+r.target_bonus:'')+(r.armored_hit!=null?' · по броне '+r.armored_hit:'')+(r.damage?' · формула '+r.damage:''))).join('')}
document.addEventListener('input',e=>{if(e.target.name==='external_bp')updateAttackPreview()});
