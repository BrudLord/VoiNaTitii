let drawnAttackPreview=null;
function carriedThrowingWeapons(c){return c.items.filter(i=>!i.equipped&&!i.data.on_ground&&i.quantity>0&&i.data.item_type==='weapon'&&i.data.dice&&i.data.keywords?.some(k=>/^Метательное(?: \d+)?$/.test(k)))}
function drawAttackButton(c){return c.editable&&c.scene_id&&carriedThrowingWeapons(c).length?btn('Достать и атаковать','draw.open'):''}
function drawWeaponForm(){
 const c=current(),items=carriedThrowingWeapons(c);
 modal('Оружие из сумки',selector('draw_item','Оружие',items,items[0]?.id)+selector('draw_mode','Стандартная атака',[{id:'ranged',name:'Метнуть'},{id:'melee',name:'В ближнем бою'}],'ranged'),async()=>{
  const f=formObject(),item=byId(items,f.draw_item);if(!item)throw Error('Выберите оружие');
  const query=new URLSearchParams({character:c.id,item:item.id,revision:item.revision,mode:f.draw_mode});
  const response=await fetch('/api/thrown-preview/?'+query),result=await response.json();
  if(!response.ok)throw Error(result.error||'Не удалось рассчитать атаку');
  drawnAttackPreview={character:result.character,payload:{item:item.id,revision:item.revision,mode:f.draw_mode},name:item.name};
  return {next:()=>drawAttackChoices()};
 },'Выбрать атаку');
}
function drawAttackChoices(){
 const preview=drawnAttackPreview,c=preview.character;
 const rank=a=>a.data.system&&a.name==='Стандартная атака'?0:a.reason?2:1;
 const abilities=c.abilities.filter(a=>a.data.weapon&&(a.data.category||'active')==='active'&&!a.data.aura).sort((a,b)=>rank(a)-rank(b));
 modal('Атака · '+preview.name,`<p class="muted">Извлечение входит в действие атаки.</p><input id="draw-attack-search" placeholder="Найти атаку" aria-label="Найти атаку"><div class="draw-attacks">${abilities.map(a=>`<div class="card" data-attack-name="${esc(a.name.toLowerCase())}"><h3>${esc(a.name)}</h3><div class="pills">${pills(a.data.keywords)}${pills(['Попадание '+(a.hit_bonus>=0?'+':'')+a.hit_bonus])}</div><p class="formula">${esc(crit?a.critical:a.formula)}</p><div class="button-group">${btn(actionNames[a.data.action||'main'],'draw.attack',`aria-label="Атаковать: ${esc(a.name)}" data-id="${a.id}" ${a.reason?'disabled':''}`)}${a.support_minor_reason===''?btn('Малым','draw.attack',`aria-label="Малым: ${esc(a.name)}" data-id="${a.id}" data-variant="minor"`):''}${a.reflex_reason===''?btn('Реакцией','draw.attack',`aria-label="Реакцией: ${esc(a.name)}" data-id="${a.id}" data-variant="reaction"`):''}</div>${a.reason?'<p class="reason">'+esc(a.reason)+'</p>':''}</div>`).join('')||'<p>Нет оружейных атак.</p>'}</div>`,null);
}
function drawAttackStart(id,variant){
 const preview=drawnAttackPreview,a=byId(preview?.character.abilities||[],id);if(!a)throw Error('Выберите оружие заново');
 abilityForm({...a,_draw_weapon:preview.payload,_draw_character:preview.character,_draw_name:preview.name,
  ...(variant==='minor'?{support_minor:true}:variant==='reaction'?{as_reaction:true}:{})});
}
function drawWeaponLog(value){return value?'<br>'+esc('Достал '+value.name+' частью атаки'):''}

document.addEventListener('input',e=>{if(e.target.id==='draw-attack-search'){const query=e.target.value.toLowerCase().trim();dialogBody.querySelectorAll('[data-attack-name]').forEach(row=>{row.hidden=!row.dataset.attackName.includes(query)})}});

function thrownWeaponNotice(a,c){if(!a.data.weapon||!c.calc.weapon_id||!a.data.keywords?.some(k=>/^Метательное(?: \d+)?$/.test(k)))return '';const item=byId(c.items,c.calc.weapon_id);return item?'<p class="muted">'+esc('После броска: '+item.name+' × 1 — на поле.')+'</p>':''}
function thrownWeaponLog(value){return value?'<br>'+esc('На поле: '+value.name+' × '+value.quantity+(value.remaining?' · в сумке осталось '+value.remaining:'')):''}
