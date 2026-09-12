const materialElements=['Изначальная','Огонь','Вода','Земля','Воздух','Тьма','Свет','Молния','Холод','Природа'];
function craftLabel(i,scope){const mods=[...(i.data.enchantments||[]),...(i.data.upgrades||[])].map(id=>entry(id)?.name).filter(Boolean);return i.name+' × '+i.quantity+(mods.length?' ['+mods.join(', ')+']':'')+' · '+scope}
function craftStock(c){return [...c.items.map(i=>({...i,label:craftLabel(i,'Личный запас')})),...S.campaigns.filter(k=>k.member&&c.memberships.some(m=>m.campaign_id===k.id)).flatMap(k=>k.items.map(i=>({...i,label:craftLabel(i,k.name)})))].filter(i=>i.quantity>0)}
function upgradeFits(item,spec){const aliases={'Лук':'Луки','Арбалет':'Арбалеты','Молот':'Молоты'};return item.data.item_type==='weapon'&&[...(item.data.families||[]),...(item.data.keywords||[])].some(k=>spec.families.includes(aliases[k]||k))}
function craftFields(spec,stock){
 if(!spec)return '';
 const ench=(S.rules.enchantments||[]).find(e=>e.id===spec.id);
 const targets=stock.filter(i=>!(i.data[spec.kind==='enchantment'?'enchantments':'upgrades']||[]).includes(spec.id)&&(spec.kind==='enchantment'?ench.types.includes(i.data.item_type):upgradeFits(i,spec)));
 const targetField=`<p class="description">${esc(entry(spec.id)?.description)}</p>`+selector('craft_item','Предмет · один экземпляр',targets.map(i=>({id:i.id,name:i.label})),null);
 if(spec.kind==='enchantment'){
  let need=50;const dust=stock.filter(i=>!i.equipped&&i.data.material_kind==='magic_dust');
  return targetField+`<h3>Магическая пыль · 50 мер</h3><div class="fields">${dust.map(i=>{const n=Math.min(need,i.quantity);need-=n;return input('supply'+i.id,i.label,n,'number',`min="0" max="${i.quantity}"`) }).join('')||'<p>Добавьте магическую пыль в инвентарь как компонент.</p>'}</div>${selector('craft_component','Стихийный компонент · '+(spec.element||'по рецепту'),stock.filter(i=>!i.equipped&&i.data.material_kind==='elemental'&&(!spec.element||i.data.element===spec.element)).map(i=>({id:i.id,name:i.label})),null)}${input('component_quantity','Количество компонента',1,'number','min="1" required')}<p id="craft-budget" class="muted" aria-live="polite"></p>`;
 }
 return targetField+`<details><summary>Материалы</summary><div class="fields">${stock.filter(i=>!i.equipped).map(i=>input('supply'+i.id,i.label,0,'number',`min="0" max="${i.quantity}"`)).join('')}</div></details>`;
}
function craftingForm(c){
 const known=new Set([...c.abilities.map(a=>a.id),...(c.knowledge||[]).filter(k=>!k.archived).map(k=>k.entry_id)]);
 const crafts=[...(c.info.craft_ids||[]).map(id=>entry(id)?.name),c.info.craft];
 const recipes=(S.rules.crafting||[]).filter(r=>known.has(r.id)&&crafts.includes(r.craft));
 if(!recipes.length){modal('Мастерская','<p>Выберите ремесло в листе персонажа и изучите рецепт улучшения в разделе знаний.</p>',null);return}
 const stock=craftStock(c);
 modal('Мастерская',`${selector('craft_recipe','Рецепт',recipes,recipes[0].id)}<div id="craft-fields">${craftFields(recipes[0],stock)}</div>`,async()=>{
  const f=formObject(),spec=recipes.find(r=>r.id===num(f.craft_recipe)),item=stock.find(i=>i.id===num(f.craft_item));
  if(!spec||!item)throw Error('Выберите рецепт и предмет');
  const supplies=stock.filter(i=>num(f['supply'+i.id])>0).map(i=>({item:i.id,revision:i.revision,quantity:Number(f['supply'+i.id]),role:spec.kind==='enchantment'?'dust':'material'}));
  if(spec.kind==='enchantment'){
   const component=stock.find(i=>i.id===num(f.craft_component));if(!component)throw Error('Выберите стихийный компонент');
   supplies.push({item:component.id,revision:component.revision,quantity:Number(f.component_quantity),role:'component'});
  }
  await api({op:'craft.apply',character:c.id,recipe:spec.id,item:item.id,item_revision:item.revision,supplies});
 },'Улучшить предмет');
 const update=()=>{
  const f=formObject(),spec=recipes.find(r=>r.id===num(f.craft_recipe));let valid=!!num(f.craft_item);
  if(spec?.kind==='enchantment'){
   const dust=stock.reduce((n,i)=>n+num(f['supply'+i.id]),0),component=stock.find(i=>i.id===num(f.craft_component)),quantity=Number(f.component_quantity);
   el('craft-budget').textContent='Магическая пыль: '+dust+' / 50';
   valid=valid&&dust===50&&!!component&&Number.isInteger(quantity)&&quantity>0&&quantity<=component.quantity;
  }
  el('dialog-submit').disabled=!valid;
 };
 el('craft-fields').addEventListener('input',update);el('craft-fields').addEventListener('change',update);
 dialogBody.querySelector('[name=craft_recipe]').addEventListener('change',e=>{el('craft-fields').innerHTML=craftFields(recipes.find(r=>r.id===num(e.target.value)),stock);update()});update();
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-do="craft.open"]');if(b)craftingForm(current())});
document.addEventListener('change',e=>{
 if(e.target.name==='material_kind'&&el('material-element'))el('material-element').hidden=e.target.value!=='elemental';
 if(e.target.id==='attack-mode')command({op:'attack.mode',character:current().id,mode:e.target.value}).catch(err=>toast(err.message));
});

function upgradeFields(data){return `<details ${data.upgrades?.length?'open':''}><summary>Улучшения оружейника</summary><div class="enchantment-choices">${(S.rules.crafting||[]).filter(r=>r.kind==='upgrade').map(r=>`<label><input type="checkbox" name="upgrades" value="${r.id}" ${data.upgrades?.includes(r.id)?'checked':''}><span><strong>${esc(r.name)}</strong><small>${esc(r.families.join(', '))}</small><small>${esc(entry(r.id)?.description)}</small></span></label>`).join('')}</div></details>`}
