function marks(c){return (c.calc.effects||[]).filter(e=>(e.status||e.name)==='Метка')}
function markSourceField(c,a){return (a.data.damage||a.data.weapon)&&marks(c).some(e=>!e.source_id)?'<label><input type="checkbox" name="mark_source_included"> Атака включает источник метки на поле</label>':''}
function markPenalty(){const ids=checks('targets');return marks(current()).some(e=>e.source_id?!ids.includes(e.source_id):!formObject().mark_source_included)?-3:0}
function externalTargetField(a){return a.data.damage||a.data.weapon?'<div id="external-bp"></div>':''}
function updateExternalTarget(){
 const box=el('external-bp');if(!box)return;
 const old=formObject().external_bp||0,prone=!!formObject().external_prone;
 box.innerHTML=checks('targets').length?'':input('external_bp','БП противника на поле',old,'number','min="0" max="1000" step="1"')+`<label><input type="checkbox" name="external_prone" ${prone?'checked':''}> Противник сбит с ног</label>`;
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
 const bonus=t?targetHitBonus(a,t):Number(formObject().external_bp||0)+(formObject().external_prone&&(a.data.keywords||[]).some(w=>/^Ближний(?:\s|$)/.test(w))?2:0),penalty=markPenalty(),total=a.hit_bonus+bonus+penalty;
 return `<div>${esc(t?t.name:'Цель на игровом поле')}: попадание <strong>${sign(total)}</strong>${penalty?' (метка −3)':''}${bonus?' (бонус цели '+sign(bonus)+')':''}${a.armored_hit_bonus!=null?' · по броне '+sign(a.armored_hit_bonus+bonus+penalty):''}<br>Формула <strong>${esc(targetDamageFormula(a,t))}</strong></div>`;
 }).join('');
}
function attackTargetLog(rows){return (rows||[]).map(r=>'<br>'+esc(r.name+': попадание '+(r.hit>=0?'+':'')+r.hit+(r.mark_penalty?' · метка '+r.mark_penalty:'')+(r.target_bonus?' · бонус цели '+r.target_bonus:'')+(r.armored_hit!=null?' · по броне '+r.armored_hit:'')+(r.damage?' · формула '+r.damage:''))).join('')}
document.addEventListener('input',e=>{if(['external_bp','external_prone','mark_source_included'].includes(e.target.name))updateAttackPreview()});
