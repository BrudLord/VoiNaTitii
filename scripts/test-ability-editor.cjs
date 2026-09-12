const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('static/app.js','utf8');
const editor=source.slice(source.indexOf('function profileToggle('),source.indexOf('function cacheNotes('));
function open(entry,character=null){
 const state={form:{data:JSON.stringify(entry.data),name:entry.name,category:'active',action:'main',circle:'0',keywords:'',formula:'',target:'single',automated:'on'},html:'',saved:null};
 for(const key of ['damage_reduction','unarmed_combat','elemental_sphere','wide_swing'])if(entry.data[key])state.form[key+'_enabled']='on';
 const context={labels:{},actionNames:{},kinds:{ability:'Умения'},catalogKind:'ability',
  input:(name,label)=>`<input name="${name}">${label}`,selector:()=>'',textArea:()=>'',effectEditor:()=>'',btn:()=>'',
  num:n=>Number(n)||0,formObject:()=>state.form,api:async p=>{state.saved=p},
  modal:(title,html,save)=>{state.html=html;state.submit=save}};
 vm.createContext(context);vm.runInContext(editor,context);context.entryForm(entry,character);return state;
}
const profiles=[
 {key:'damage_reduction',name:'Парирующие потоки',value:{divisor:2,unarmed:true},changed:{divisor:3,unarmed:false},field:'defense_divisor',fields:{defense_divisor:'4',defense_unarmed:'on'},result:{divisor:4,unarmed:true}},
 {key:'unarmed_combat',name:'Бой без оружия',value:{dice:'1к8',ignore_requirements:true},changed:{dice:'2к6',ignore_requirements:false},field:'unarmed_dice',fields:{unarmed_dice:'3к4'},result:{dice:'3к4',ignore_requirements:false}},
 {key:'elemental_sphere',name:'Элементальная сфера',value:{strength:1},changed:{strength:5},field:'sphere_strength',fields:{sphere_strength:'2'},result:{strength:2}},
 {key:'wide_swing',name:'Широкий замах',value:{hit:1,reach:1},changed:{hit:3,reach:4},field:'swing_hit',fields:{swing_hit:'2',swing_reach:'3'},result:{hit:2,reach:3}},
];
for(const profile of profiles){
 test(`${profile.name}: switch disables and restores the mechanic without JSON`,async()=>{
  const enabled=open({id:9,name:profile.name,data:{[profile.key]:profile.value}});
  Object.assign(enabled.form,profile.fields);delete enabled.form[profile.key+'_enabled'];await enabled.submit();
  assert.equal(enabled.saved.data[profile.key],null);
  const disabled=open({id:9,name:profile.name,data:enabled.saved.data});
  Object.assign(disabled.form,profile.fields,{[profile.key+'_enabled']:'on'});await disabled.submit();
  assert.equal(JSON.stringify(disabled.saved.data[profile.key]),JSON.stringify(profile.result));
 });
 test(`${profile.name}: explicit disabling survives the actual editor save`,async()=>{
  const s=open({id:9,name:profile.name,data:{[profile.key]:null}});
  assert.match(s.html,new RegExp('name="'+profile.key+'_enabled" >')); 
  await s.submit();assert.equal(s.saved.data[profile.key],null);
 });
 test(`${profile.name}: typed controls work after a rename`,async()=>{
  const s=open({id:9,name:'Моя версия',data:{[profile.key]:profile.value}},{id:5,revision:7});
  assert.match(s.html,new RegExp('name="'+profile.field+'"'));
  Object.assign(s.form,profile.fields);await s.submit();
  assert.equal(JSON.stringify(s.saved.data[profile.key]),JSON.stringify(profile.result));
  assert.equal(s.saved.op,'character.ability.save');assert.equal(s.saved.character,5);assert.equal(s.saved.revision,7);
 });
 test(`${profile.name}: advanced edits and removal are not overwritten by stale controls`,async()=>{
  for(const advanced of [profile.changed,null,undefined]){
   const s=open({id:9,name:profile.name,data:{[profile.key]:profile.value}});
   Object.assign(s.form,profile.fields,{data:JSON.stringify(advanced===undefined?{}:{[profile.key]:advanced})});
   await s.submit();assert.equal(JSON.stringify(s.saved.data[profile.key]),JSON.stringify(advanced));
  }
 });
}
test('profiles added through advanced parameters remain intact',async()=>{
 const s=open({id:9,name:'Новое умение',data:{}}),data=Object.fromEntries(profiles.map(p=>[p.key,p.changed]));
 s.form.data=JSON.stringify(data);await s.submit();
 for(const p of profiles)assert.equal(JSON.stringify(s.saved.data[p.key]),JSON.stringify(p.changed));
});
