const itemTypes={currency:'Золото',material:'Компонент',weapon:'Оружие',focus:'Фокусировка',armor:'Доспех',shield:'Щит',consumable:'Расходник',other:'Прочее'};
let itemDraft=null;
function inferredItemType(item){return item?.data.item_type||(item?.name==='Золото'?'currency':item?.data.dice?'weapon':item?.data.armor?'armor':'other')}
function itemTypeFields(type,d,item){
 const equipment=['weapon','focus','armor','shield'].includes(type);
 if(type==='currency')return input('quantity','Количество',item.quantity??0,'number','min="0" required');
 return `<div class="fields">${input('item_name','Название',item.name||'','text','required maxlength="160"')}${input('quantity','Количество',item.quantity??1,'number','min="0" required')}${type==='weapon'?input('dice','Урон оружия',d.dice||'','text','placeholder="1к6"')+selector('stat','Характеристика',Object.entries(labels).map(([id,name])=>({id,name})),d.stat||'str')+input('crit','Дополнительный Крит',d.crit||0,'number','min="0"'):''}${['armor','shield'].includes(type)?input('armor',type==='armor'?'Защита доспеха':'Защита щита',d.armor||0,'number','min="0"'):''}${type==='material'?selector('material_kind','Вид компонента',[{id:'magic_dust',name:'Магическая пыль'},{id:'elemental',name:'Стихийный'},{id:'other',name:'Прочий материал'}],d.material_kind||'other')+`<div id="material-element" ${d.material_kind!=='elemental'?'hidden':''}>${selector('element','Стихия',materialElements.map(name=>({id:name,name})),d.element)}</div>`:''}${equipment?input('keywords','Свойства',(d.keywords||[]).join(', '),'text','placeholder="Кинжалы, Лёгкое"'):''}</div>${textArea('description',type==='consumable'?'Эффект и применение':'Описание',d.description||'')}${equipment?`<details><summary>Дополнительные бонусы</summary><div class="fields">${[['hit','Попадание'],['damage','Урон'],['ac','КД'],['speed','Скорость'],['max_hp','Максимум ХП']].map(([stat,name])=>input('bonus_'+stat,name,d.effects?.find(e=>e.key==='item_bonus:'+stat)?.value||0,'number')).join('')}</div></details>`:''}${type==='weapon'?upgradeFields(d):''}${equipment?enchantmentFields(type,d):''}${itemDraft.charId&&equipment?`<label class="checks"><input name="equipped" type="checkbox" ${item.equipped?'checked':''}>Надето / в руках</label>`:''}`;
}
// Replace the old all-fields form with type-specific fields; catalogue metadata is retained.
function itemForm(item=null,charId=null,campId=null){
 itemDraft={item:item||{quantity:1,name:'',equipped:false},data:structuredClone(item?.data||{}),charId,campId,entryId:item?.entry_id||null};
 modal(item?'Изменить предмет':'Добавить предмет',`<div class="fields">${selector('item_type','Тип',Object.entries(itemTypes).map(([id,name])=>({id,name})),inferredItemType(item))}<label id="typed-template-label" ${inferredItemType(item)==='currency'?'hidden':''}>Справочник<select id="typed-item-template">${options(S.catalog.filter(e=>e.kind==='item'),null,'Свой предмет')}</select></label></div><div id="typed-item-fields">${itemTypeFields(inferredItemType(item),itemDraft.data,itemDraft.item)}</div>`,async()=>{
  const f=formObject(),type=f.item_type;if(!itemTypes[type])throw Error('Выберите тип предмета');
  const equipment=['weapon','focus','armor','shield'].includes(type);
  const data={...itemDraft.data,item_type:type,description:f.description||''};
  delete data.material_kind;delete data.element;
  if(type==='material'){data.material_kind=f.material_kind||'other';data.element=f.material_kind==='elemental'?f.element:''}
  for(const key of ['dice','crit','armor','stat'])delete data[key];
  if(type==='weapon')Object.assign(data,{dice:f.dice||'',crit:num(f.crit),stat:f.stat||'str'});
  if(['armor','shield'].includes(type))data.armor=num(f.armor);
  if(equipment){
   data.upgrades=type==='weapon'?[...dialogBody.querySelectorAll('[name=upgrades]:checked')].map(e=>num(e.value)):[];
   data.enchantments=[...dialogBody.querySelectorAll('[name=enchantments]:checked')].map(e=>num(e.value));
   data.keywords=(f.keywords||'').split(',').map(s=>s.trim()).filter(Boolean);
   const schools=S.catalog.filter(e=>e.kind==='school').map(e=>e.name);data.families=data.keywords.filter(k=>schools.includes(k));
   data.effects=(data.effects||[]).filter(e=>!String(e.key||'').startsWith('item_bonus:'));
   for(const stat of ['hit','damage','ac','speed','max_hp'])if(num(f['bonus_'+stat]))data.effects.push({key:'item_bonus:'+stat,stat,value:num(f['bonus_'+stat])});
  }else{delete data.upgrades;delete data.enchantments;delete data.effects;delete data.keywords;delete data.families}
  await api({op:'item.save',id:item?.id,revision:item?.revision,character:charId,campaign:campId,entry:type==='currency'?null:itemDraft.entryId,name:type==='currency'?'Золото':f.item_name,quantity:num(f.quantity),slot:item?.slot||'',equipped:equipment&&!!f.equipped,data:type==='currency'?{item_type:'currency'}:data});
 });
}
document.addEventListener('change',e=>{
 if(!el('typed-item-fields')||!itemDraft)return;const t=e.target;
 if(t.name==='item_type'){
  el('typed-template-label').hidden=t.value==='currency';
  const f=formObject();Object.assign(itemDraft.item,{name:f.item_name||itemDraft.item.name,quantity:num(f.quantity),equipped:!!f.equipped});
  for(const key of ['description','dice','stat'])if(key in f)itemDraft.data[key]=f[key];
  for(const key of ['armor','crit'])if(key in f)itemDraft.data[key]=num(f[key]);
  if('keywords'in f)itemDraft.data.keywords=f.keywords.split(',').map(x=>x.trim()).filter(Boolean);
  itemDraft.data.enchantments=[...dialogBody.querySelectorAll('[name=enchantments]:checked')].map(e=>num(e.value));
  el('typed-item-fields').innerHTML=itemTypeFields(t.value,itemDraft.data,itemDraft.item);
 }
 if(t.id==='typed-item-template'){
  const selected=entry(t.value);if(!selected){itemDraft.entryId=null;return}
  itemDraft.data=structuredClone(selected.data);itemDraft.item={...itemDraft.item,name:selected.name};itemDraft.entryId=selected.id;
  const type=inferredItemType({data:selected.data,name:selected.name});
  const typeSelect=dialogBody.querySelector('[name=item_type]');typeSelect.value=itemTypes[type]?type:'other';typeSelect.dispatchEvent(new Event('change',{bubbles:true}));
  // The source name and values take precedence over a previous draft.
  itemDraft.data=structuredClone(selected.data);itemDraft.item.name=selected.name;
  el('typed-item-fields').innerHTML=itemTypeFields(typeSelect.value,itemDraft.data,itemDraft.item);
 }
});
function stockItem(id){for(const c of S.characters){const item=byId(c.items,id);if(item)return {...item,character:c.id,campaign:null}}for(const c of S.campaigns){const item=byId(c.items,id);if(item)return {...item,character:null,campaign:c.id}}return null}
function stockUndo(){return `<div class="toolbar stock-undo">${btn('↶ Отмена','undo')}${btn('↷ Повтор','redo')}</div>`}
function transferItemForm(item){
 const source=item.character?byId(S.characters,item.character):null;
 const campaigns=source?source.memberships.map(m=>m.campaign_id):[item.campaign];
 const chars=S.characters.filter(c=>c.id!==source?.id&&!c.scene_id&&(item.campaign?c.memberships.some(m=>campaigns.includes(m.campaign_id)):c.owner_id===S.user.id||S.user.master||c.memberships.some(m=>campaigns.includes(m.campaign_id))));
 const choices=[...chars.map(c=>({id:'character:'+c.id,name:c.name+' · '+c.owner})),...S.campaigns.filter(c=>source&&c.member&&campaigns.includes(c.id)).map(c=>({id:'campaign:'+c.id,name:'Общий запас · '+c.name}))];
 modal('Передать · '+item.name,`${input('quantity','Количество',item.quantity,'number',`min="1" max="${item.quantity}" required`)}${selector('destination','Получатель',choices,null)}`,async()=>{
  const f=formObject(),[kind,id]=(f.destination||'').split(':');if(!['character','campaign'].includes(kind)||!num(id))throw Error('Выберите получателя');
  await api({op:'item.transfer',id:item.id,revision:item.revision,quantity:Number(f.quantity),[kind]:num(id)});
 },'Передать');
}
function consumeItemForm(item){modal('Списать · '+item.name,`${input('quantity','Количество',1,'number',`min="1" max="${item.quantity}" required`)}${input('reason','На что потрачено / причина','')}`,async()=>api({op:'item.consume',id:item.id,revision:item.revision,quantity:Number(formObject().quantity),reason:formObject().reason}),'Списать')}
document.addEventListener('click',e=>{const b=e.target.closest('[data-do="item.consume"]');if(b)consumeItemForm(stockItem(b.dataset.id))});

function equipButton(item,owner){
 const battle=!!owner?.scene_id,weapon=item.data.item_type==='weapon';
 const quick=!item.equipped&&weapon&&(item.data.keywords||[]).some(k=>['Лёгкое','Легкое','Резервное'].includes(k));
 const reason=!item.quantity?'Нет предмета':battle&&item.data.item_type==='armor'?'Доспех меняется вне боя':battle?(quick?owner.minor_action_reason:owner.main_action_reason):'';
 const title=item.equipped?'Снять':weapon?'Достать':'Надеть';
 return btn(title+(battle?' · '+(quick?'малое':'основное'):''),'item.equip',`data-id="${item.id}" ${reason?'disabled title="'+esc(reason)+'"':''}`);
}
