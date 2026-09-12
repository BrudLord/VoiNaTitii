/* Preview the same ordered status transitions used by the server. */
function reactionStatus(e){
 if(e.status)return e.status;
 const name=(e.name||'').replace(/\s+[+-]?\d+$/,'');
 const profile=S.rules?.status_profiles?.[name];
 return profile&&(!e.stat||e.stat===profile[0])?name:'';
}
function reactionOptions(c,e){
 const name=reactionStatus(e),elemental=['Поджог','Влага','Кислота','Шок','Мороз','Яд','Благословение','Проклятье',...(S.rules?.constructive||[]).map(r=>r[2])];
 return (c.runtime.effects||[]).flatMap(old=>{
  const other=reactionStatus(old);if(!name||!other||name===other)return [];
  const same=pair=>pair.slice(0,2).includes(name)&&pair.slice(0,2).includes(other);
  const result=name==='Рассеивание'&&['Поджог','Влага','Кислота','Яд','Мороз'].includes(other)?'Рассеивание':name==='Насыщение'&&elemental.includes(other)?'Насыщение':(S.rules?.neutral||[]).some(same)?'Нейтрализация':(S.rules?.constructive||[]).find(same)?.[2];
  const strength=result==='Рассеивание'?Math.abs(e.value||0):Math.abs(old.value||0)+Math.abs(e.value||0);
  return result?[{id:old.key,name:result+(result==='Нейтрализация'?'':' '+strength)+' · '+other,reaction:result,strength,effect:old}]:[];
 });
}
function reactionSequence(target,effects,selected,spreads={},world=null){
 const state={runtime:{effects:JSON.parse(JSON.stringify(target.runtime.effects||[]))}},rows=[];
 for(const original of effects){
  if(original.manual||['hp','temp'].includes(original.stat))continue;
  let e={...original},name=reactionStatus(e),choices=reactionOptions(state,e),choice=choices.find(c=>String(c.id)===String(selected[e.index]));
  if(choices.length){
   rows.push({index:e.index,choices,selected:choice?.id,spreadWorld:world?JSON.parse(JSON.stringify(world)):null});
   if(!choice)break;
   const old=state.runtime.effects.find(o=>o.key===choice.id);
   state.runtime.effects=state.runtime.effects.filter(o=>o!==old);
   if(choice.reaction==='Рассеивание'){
    const spread=spreads[e.index]||{};
    if(world)for(const id of spread.targets||[]){if(world[id]&&id!==target.id)reactionSequence(world[id],[{...old,index:0}],{0:spread.reactions?.[id]},{},world)}
    if(!spread.remove_source)state.runtime.effects.push(old);continue
   }
   if(['Нейтрализация','Взрыв','Проклятый разряд','Ледяная тьма'].includes(choice.reaction))continue;
   if(choice.reaction==='Насыщение'){state.runtime.effects.push({...old,value:old.value<0?-choice.strength:choice.strength});continue}
   name=choice.reaction;e={...e,status:name,name,stat:name==='Размякшая плоть'?'damage':'status',value:name==='Размякшая плоть'?-choice.strength:choice.strength};
  }else if(['Насыщение','Рассеивание'].includes(name))continue;
  e.key=name?'status:'+name:e.key;e.status=name;
  const old=state.runtime.effects.find(o=>['Оглушение','Оцепенение','Заморозка'].includes(name)?reactionStatus(o)===name:o.key===e.key);
  if(old){e.value=['Оглушение','Оцепенение','Заморозка'].includes(name)?old.value+e.value:Math.abs(old.value)>Math.abs(e.value)?old.value:e.value;state.runtime.effects=state.runtime.effects.filter(o=>o!==old)}
  state.runtime.effects.push(e);
 }
 if(world&&target.id)world[target.id].runtime.effects=state.runtime.effects;
 return rows;
}
