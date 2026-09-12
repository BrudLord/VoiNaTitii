function enchantmentFields(type,data){
 const choices=(S.rules.enchantments||[]).filter(e=>e.types.includes(type));
 if(!choices.length)return '';
 return `<details ${data.enchantments?.length?'open':''}><summary>Зачарования · ${data.enchantments?.length||0}</summary><div class="enchantment-choices">${choices.map(e=>`<label><input type="checkbox" name="enchantments" value="${e.id}" ${data.enchantments?.includes(e.id)?'checked':''}><span><strong>${esc(e.name)}</strong><small>${esc(e.description)}</small></span></label>`).join('')}</div></details>`;
}
function enchantmentSummary(item){return (item.data.enchantments||[]).map(id=>{const e=(S.rules.enchantments||[]).find(x=>x.id===id);return e?`<details class="item-enchantment"><summary>${esc(e.name)}</summary><p>${esc(e.description)}</p></details>`:''}).join('')}
function enchantmentKnowledge(c){
 const known=new Set(c.abilities.map(a=>a.id));const entries=(S.rules.enchantments||[]).filter(e=>known.has(e.id));
 return `<div class="toolbar"><h2>Изученные зачарования</h2>${c.editable?btn('+ Изучить','enchantment.learn'):''}</div>${entries.map(e=>`<article class="card"><div class="card-title"><h3>${esc(e.name)}</h3>${c.editable?btn('Убрать','enchantment.forget',`data-id="${e.id}"`):''}</div><p class="description">${esc(e.description)}</p><small>Предметы: ${c.items.filter(i=>i.data.enchantments?.includes(e.id)).map(i=>esc(i.name)).join(', ')||'—'}</small></article>`).join('')||'<div class="empty">Здесь можно хранить изученные чары и видеть связанные с ними вещи.</div>'}`;
}
function initiativeForm(session){
 const chars=S.characters.filter(c=>session.characters.includes(c.id));
 modal('Начать бой · '+session.name,`<p>Каждый бросает 2к6. Затем распределите полученные результаты между персонажами.</p><div class="initiative-pool">${chars.map((c,i)=>input('pool'+i,'Бросок · '+c.name,'','number','min="2" max="12" required')).join('')}</div><h3>Распределение</h3><div class="initiative-assign">${chars.map((c,i)=>`<div class="card">${selector('assigned'+c.id,c.name,chars.map((x,n)=>({id:n,name:'Бросок '+(n+1)+' · '+x.name})),i)}<small>Ловкость и бонусы: ${c.calc.initiative>=0?'+':''}${c.calc.initiative}</small><strong id="initiative-total-${c.id}">—</strong></div>`).join('')}</div>`,async()=>{
  const f=formObject(),rolls=chars.map((c,i)=>Number(f['pool'+i])),assigned=Object.fromEntries(chars.map(c=>[c.id,f['assigned'+c.id]===''?null:Number(f['assigned'+c.id])]));
  if(Object.values(assigned).includes(null)||new Set(Object.values(assigned)).size!==chars.length)throw Error('Каждый бросок должен достаться ровно одному персонажу');
  await api({op:'scene.start',session:session.id,roll_pool:rolls,assigned_rolls:assigned});
 },'Начать бой');
 const update=()=>{const f=formObject();for(const c of chars){const raw=f['pool'+f['assigned'+c.id]];el('initiative-total-'+c.id).textContent=raw?`Инициатива: ${Number(raw)+c.calc.initiative}`:'—'}};
 for(const container of dialogBody.querySelectorAll('.initiative-pool,.initiative-assign')){container.addEventListener('input',update);container.addEventListener('change',update)}
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-do]');if(!b)return;
 try{
 if(b.dataset.do==='enchantment.learn'){
  const c=current(),known=new Set(c.abilities.map(a=>a.id));
  modal('Изучить зачарование',selector('entry','Зачарование',(S.rules.enchantments||[]).filter(e=>!known.has(e.id)),null),async()=>api({op:'enchantment.learn',character:c.id,entry:num(formObject().entry)}),'Изучить');
 }
 if(b.dataset.do==='enchantment.forget')await command({op:'enchantment.learn',character:current().id,entry:num(b.dataset.id),remove:true});
 if(b.dataset.do==='enchantment.kill'){
  const c=current();modal('Первый поверженный противник','<p>Отметить первое убийство в этом бою? Применятся фиксированные лечебные чары надетых предметов.</p>',async()=>api({op:'enchantment.kill',character:c.id}),'Отметить');
 }
 }catch(err){toast(err.message)}
});
document.addEventListener('change',e=>{if(e.target.id==='focus-picker')command({op:'focus.select',character:current().id,item:num(e.target.value)}).catch(err=>toast(err.message))});
