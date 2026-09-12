function disarmButton(c){return c.disarm&&c.editable?btn('Обезоружить','weapon.disarm',c.disarm.reason?'disabled title="'+esc(c.disarm.reason)+'"':''):''}
function disarmForm(c){
 const scene=byId(S.scenes,c.scene_id),targets=scene.state.order.map(id=>byId(S.characters,id)).filter(t=>t.id!==c.id);
 modal('Обезоруживание',`<p>${pills(c.disarm.keywords)} · попадание ${c.disarm.hit>=0?'+':''}${c.disarm.hit}</p>${selector('disarm_target','Цель',[{id:0,name:'Противник на поле'},...targets],0)}<div id="disarm-items"></div><label><input name="in_range" type="checkbox" required> Цель в пределах досягаемости</label>${c.disarm.roll_conditions?.length?'<p class="notice">'+esc(c.disarm.roll_conditions.join(' · '))+'</p>':''}${input('roll_result','Физический бросок на попадание','','text','required')}${selector('outcome','Результат',[{id:'hit',name:'Попадание'},{id:'miss',name:'Промах'}],'hit')}`,async()=>{const f=formObject();return api({op:'weapon.disarm',character:c.id,target:Number(f.disarm_target||0),item:Number(f.disarm_item||0),external_item:f.external_item,roll_result:f.roll_result,outcome:f.outcome,in_range:!!f.in_range,external_bp:Number(f.external_bp||0),mark_source_included:!!f.mark_source_included})},'Применить');
 updateDisarmItems();
}
function updateDisarmItems(){
 const id=Number(formObject().disarm_target||0),t=byId(S.characters,id),c=current();
 el('disarm-items').innerHTML=t?selector('disarm_item','Предмет в руках',t.items.filter(i=>i.equipped&&i.quantity>0&&['weapon','shield','focus'].includes(i.data.item_type)),null):input('external_item','Что роняет противник','','text','required maxlength="160"')+input('external_bp','БП противника',0,'number','min="0" max="1000"');
 el('disarm-items').innerHTML+='<p id="disarm-hit"></p>';
 if(marks(c).some(e=>!e.source_id))el('disarm-items').innerHTML+='<label><input type="checkbox" name="mark_source_included"> Цель — источник метки на поле</label>';
 updateDisarmHit();
}
function updateDisarmHit(){const box=el('disarm-hit');if(!box)return;const c=current(),f=formObject(),id=Number(f.disarm_target||0),t=byId(S.characters,id),bonus=t?targetHitBonus({data:{keywords:c.disarm.keywords},hit_scope:'weapon'},t):Number(f.external_bp||0),penalty=marks(c).some(e=>e.source_id?e.source_id!==id:!f.mark_source_included)?-3:0,total=c.disarm.hit+bonus+penalty;box.textContent='Попадание '+(total>=0?'+':'')+total;}
function disarmLog(value){return value?'<br>'+esc('Обезоруживание · '+value.target+': '+(value.hit?'роняет '+value.item:'промах, предмет остаётся в руках')):''}
document.addEventListener('change',e=>{if(e.target.name==='disarm_target')updateDisarmItems()});

document.addEventListener("input",e=>{if(["external_bp","mark_source_included"].includes(e.target.name))updateDisarmHit()});
