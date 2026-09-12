const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function setup(){
 const item={id:2,revision:4,name:'Кинжал',quantity:1,equipped:false,data:{item_type:'weapon',dice:'1к4',keywords:['Метательное 5']}},character={id:1,scene_id:9,editable:true,items:[item],abilities:[]};
 const state={character,form:{draw_item:'2',draw_mode:'ranged'},requests:[],opened:null};
 const context={document:{addEventListener(){}},current:()=>character,formObject:()=>state.form,btn:(text,action,extra)=>`<button data-do="${action}" ${extra}>${text}</button>`,selector:()=>'',esc:String,pills:words=>(words||[]).join(' · '),crit:false,actionNames:{main:'Основное'},byId:(xs,id)=>xs.find(x=>x.id===Number(id)),URLSearchParams,
  modal:(title,html,save,label)=>{state.modal={title,html,save,label}},abilityForm:a=>{state.opened=a},
  fetch:async url=>{state.requests.push(url);return {ok:true,json:async()=>({character:state.preview||character})}}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/thrown.js','utf8'),context);return {context,state,item};
}
test('draw menu accepts only carried, usable throwing weapons',()=>{
 const {context,state,item}=setup();state.character.items=[item,{...item,id:3,equipped:true},{...item,id:4,quantity:0},{...item,id:5,data:{...item.data,on_ground:true}},{...item,id:6,data:{...item.data,keywords:['Лёгкое']}}];
 assert.equal(context.carriedThrowingWeapons(state.character).length,1);assert.match(context.drawAttackButton(state.character),/Достать и атаковать/);
 state.character.editable=false;assert.equal(context.drawAttackButton(state.character),'');
});
test('preview makes a read-only request and attack form retains the chosen weapon and modifier',async()=>{
 const {context,state}=setup();state.preview={...state.character,calc:{weapon_id:2},abilities:[{id:8,name:'Стандартная атака',data:{weapon:true,action:'main',keywords:['Дальнобойный 5']},formula:'1к4 + 3',critical:'2к4 + 3',hit_bonus:3,reason:''}]};
 context.drawWeaponForm();const next=await state.modal.save();
 assert.equal(state.requests.length,1);assert.match(state.requests[0],/^\/api\/thrown-preview\/\?/);assert.match(state.requests[0],/revision=4/);
 next.next();assert.match(state.modal.html,/1к4 \+ 3/);assert.match(state.modal.html,/Попадание \+3/);
 context.drawAttackStart(8);
 assert.equal(state.opened._draw_weapon.item,2);assert.equal(state.opened._draw_weapon.revision,4);assert.equal(state.opened._draw_character.calc.weapon_id,2);
});
test('unavailable attacks stay disabled while an allowed minor variant can be selected',async()=>{
 const {context,state}=setup();state.preview={...state.character,abilities:[{id:8,name:'Атака',data:{weapon:true},formula:'1к4',hit_bonus:0,reason:'Нет основного действия',support_minor_reason:''}]};
 context.drawWeaponForm();(await state.modal.save()).next();
 assert.match(state.modal.html,/data-id="8" disabled/);assert.match(state.modal.html,/data-variant="minor"/);
 context.drawAttackStart(8,'minor');assert.equal(state.opened.support_minor,true);
});
test('failed preview does not open an attack with invented calculations',async()=>{
 const {context,state}=setup();context.fetch=async()=>({ok:false,json:async()=>({error:'Предмет уже изменился'})});
 context.drawWeaponForm();await assert.rejects(state.modal.save(),/Предмет уже изменился/);assert.equal(state.opened,null);
});
test('journal names the drawn item',()=>{const {context}=setup();assert.match(context.drawWeaponLog({name:'Дротик',mode:'ranged'}),/Достал Дротик частью атаки/);assert.equal(context.drawWeaponLog(null),'')});

test('temporary weapon calculations belong only to the attack dialog',()=>{
 const source=fs.readFileSync('static/app.js','utf8'),elements={},base={id:1,calc:{weapon_id:0}},draft={id:1,calc:{weapon_id:2}};
 const context={S:{characters:[base]},characterId:1,byId:(xs,id)=>xs.find(x=>x.id===id),dialog:{open:false,showModal(){this.open=true}},dialogBody:{},el:id=>elements[id]||(elements[id]={})};
 vm.createContext(context);
 vm.runInContext(source.slice(source.indexOf('let abilityContext='),source.indexOf('const btn=')),context);
 for(const name of ['modal','abilityForm']){const start=source.indexOf('function '+name+'(');vm.runInContext(source.slice(start,source.indexOf('\n',start)),context)}
 context.openAbilityForm=()=>{assert.equal(vm.runInContext('current().calc.weapon_id',context),2);context.modal('Атака','',()=>{})};
 context.abilityForm({_draw_character:draft});assert.equal(vm.runInContext('current().calc.weapon_id',context),2);
 context.dialog.open=false;assert.equal(vm.runInContext('current().calc.weapon_id',context),0);
 context.modal('Обычная форма','',()=>{});assert.equal(vm.runInContext('current().calc.weapon_id',context),0);
 context.dialog.open=false;context.openAbilityForm=()=>{throw Error('Ошибка формы')};
 assert.throws(()=>context.abilityForm({_draw_character:draft}),/Ошибка формы/);assert.equal(vm.runInContext('current().calc.weapon_id',context),0);
});
