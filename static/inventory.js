const itemTypes={currency:'Золото',weapon:'Оружие',armor:'Доспех',shield:'Щит',consumable:'Расходник',other:'Прочее'};
let itemDraft=null;
function inferredItemType(item){return item?.data.item_type||(item?.name==='Золото'?'currency':item?.data.dice?'weapon':item?.data.armor?'armor':'other')}
function itemTypeFields(type,d,item){
 const equipment=['weapon','armor','shield'].includes(type);
 if(type==='currency')return input('quantity','Количество',item.quantity??0,'number','min="0" required');
 return `<div class="fields">${input('item_name','Название',item.name||'','text','required maxlength="160"')}${input('quantity','Количество',item.quantity??1,'number','min="0" required')}${type==='weapon'?input('dice','Урон оружия',d.dice||'','text','placeholder="1к6"')+selector('stat','Характеристика',Object.entries(labels).map(([id,name])=>({id,name})),d.stat||'str')+input('crit','Дополнительный Крит',d.crit||0,'number','min="0"'):''}${['armor','shield'].includes(type)?input('armor',type==='armor'?'Защита доспеха':'Защита щита',d.armor||0,'number','min="0"'):''}${equipment?input('keywords','Свойства',(d.keywords||[]).join(', '),'text','placeholder="Кинжалы, Лёгкое"'):''}</div>${textArea('description',type==='consumable'?'Эффект и применение':'Описание',d.description||'')}${equipment?`<details><summary>Дополнительные бонусы</summary><div class="fields">${[['hit','Попадание'],['damage','Урон'],['ac','КД'],['speed','Скорость'],['max_hp','Максимум ХП']].map(([stat,name])=>input('bonus_'+stat,name,d.effects?.find(e=>e.key==='item_bonus:'+stat)?.value||0,'number')).join('')}</div></details>`:''}${itemDraft.charId&&equipment?`<label class="checks"><input name="equipped" type="checkbox" ${item.equipped?'checked':''}>Надето / в руках</label>`:''}`;
}
// Replace the old all-fields form with type-specific fields; catalogue metadata is retained.
function itemForm(item=null,charId=null,campId=null){
 itemDraft={item:item||{quantity:1,name:'',equipped:false},data:structuredClone(item?.data||{}),charId,campId,entryId:item?.entry_id||null};
 modal(item?'Изменить предмет':'Добавить предмет',`<div class="fields">${selector('item_type','Тип',Object.entries(itemTypes).map(([id,name])=>({id,name})),inferredItemType(item))}<label id="typed-template-label" ${inferredItemType(item)==='currency'?'hidden':''}>Справочник<select id="typed-item-template">${options(S.catalog.filter(e=>e.kind==='item'),null,'Свой предмет')}</select></label></div><div id="typed-item-fields">${itemTypeFields(inferredItemType(item),itemDraft.data,itemDraft.item)}</div>`,async()=>{
  const f=formObject(),type=f.item_type;if(!itemTypes[type])throw Error('Выберите тип предмета');
  const equipment=['weapon','armor','shield'].includes(type);
  const data={...itemDraft.data,item_type:type,description:f.description||''};
  for(const key of ['dice','crit','armor','stat'])delete data[key];
  if(type==='weapon')Object.assign(data,{dice:f.dice||'',crit:num(f.crit),stat:f.stat||'str'});
  if(['armor','shield'].includes(type))data.armor=num(f.armor);
  if(equipment){
   data.keywords=(f.keywords||'').split(',').map(s=>s.trim()).filter(Boolean);
   const schools=S.catalog.filter(e=>e.kind==='school').map(e=>e.name);data.families=data.keywords.filter(k=>schools.includes(k));
   data.effects=(data.effects||[]).filter(e=>!String(e.key||'').startsWith('item_bonus:'));
   for(const stat of ['hit','damage','ac','speed','max_hp'])if(num(f['bonus_'+stat]))data.effects.push({key:'item_bonus:'+stat,stat,value:num(f['bonus_'+stat])});
  }
  await api({op:'item.save',id:item?.id,character:charId,campaign:campId,entry:type==='currency'?null:itemDraft.entryId,name:type==='currency'?'Золото':f.item_name,quantity:num(f.quantity),slot:item?.slot||'',equipped:equipment&&!!f.equipped,data:type==='currency'?{item_type:'currency'}:data});
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
