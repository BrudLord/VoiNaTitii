const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function setup(){
 const c={id:1,scene_id:1,name:'Игрок',runtime:{},calc:{speed:6}},nodes={};let save;
 const ctx={S:{revision:12,characters:[c,{id:2,name:'Союзник'}],scenes:[{id:1,state:{order:[1,2]}}]},current:()=>c,byId:(xs,id)=>xs.find(x=>x.id===Number(id)),esc:s=>String(s??'').replaceAll('<','&lt;'),options:()=>'',input:()=>'',btn:()=>'',readyPayload:()=>({}),modal:(title,html,callback)=>{save=callback;ctx.html=html},el:id=>nodes[id]||null,document:{addEventListener(){}},dialogBody:{querySelectorAll:()=>[],querySelector:selector=>({value:ctx.formObject()[selector.match(/name="([^"]+)"/)[1]]||''})},crypto:{randomUUID:()=> 'series-key'},csrf:()=>'',formObject:()=>({}),attackTargetLog:()=>'',movementLog:()=>'',fetch:async(url,args)=>{ctx.request={url,body:JSON.parse(args.body)};return {ok:true,json:async()=>ctx.response}},api:async p=>{ctx.writes.push(p);return {ok:true}},writes:[],response:{characters:[c],inputs:{attack_sequence:{attacks:[]}}}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('static/sequences.js','utf8'),ctx);
 return {ctx,nodes,save:()=>save,run:s=>vm.runInContext(s,ctx)};
}
test('planning the sequence makes only a preview request, with all recipients and revision',async()=>{
 const t=setup();t.ctx.formObject=()=>({'series_target:0':'2','series_target:1':'','series_external:1':'Гоблин'});t.nodes['series-targets']={dataset:{groups:2}};
 t.ctx.sequenceForm({id:7,name:'Осколки',description:'',attack_sequence:{count:2,targets:'any'}});await t.save()();
 assert.equal(t.ctx.request.url,'/api/sequence-preview/');assert.equal(t.ctx.request.body.completed,0);assert.equal(t.ctx.request.body.sequence_revision,12);
 assert.deepEqual(t.ctx.request.body.attacks,[{target:2,external_target:''},{target:null,external_target:'Гоблин'}]);assert.equal(t.ctx.writes.length,0);
});
test('a canceled pending preview never starts a new sequence',async()=>{
 const t=setup();t.ctx.formObject=()=>({'series_target:0':'2'});t.nodes['series-targets']={dataset:{groups:1}};
 let finish;t.ctx.fetch=()=>new Promise(resolve=>{finish=resolve});t.ctx.sequenceForm({id:7,name:'Удары',attack_sequence:{count:2,targets:'same'}});
 const pending=t.save()();t.ctx.clearSequence();finish({ok:true,json:async()=>t.ctx.response});await pending;assert.equal(t.run('sequenceCapture'),null);
});
test('a completed attack copies only attack fields and leaves the future plan unrolled',async()=>{
 const t=setup();t.run("sequenceCapture={index:0,root:{character:1,ability:7,sequence_revision:12},plan:[{target:2,external_target:''},{target:2,external_target:''}],forms:[]}");
 await t.ctx.submitSequence({character:999,ability:999,outcome:'critical',roll_result:'20; урон 8',reactions:{},draw_weapon:{item:6}});
 const body=t.ctx.request.body;assert.equal(body.completed,1);assert.equal(body.character,1);assert.equal(body.ability,7);assert.equal(body.attacks[0].outcome,'critical');assert.equal(body.attacks[1].outcome,undefined);assert.equal(body.attacks[0].draw_weapon,undefined);assert.equal(t.ctx.writes.length,0);
});
test('failed preview preserves existing rolls for correction',async()=>{
 const t=setup();t.run("sequenceCapture={index:0,root:{},plan:[{target:2,roll_result:'старый'}],forms:[]}");t.ctx.fetch=async()=>({ok:false,json:async()=>({error:'Реакция изменилась'})});
 await assert.rejects(()=>t.ctx.submitSequence({outcome:'hit',roll_result:'новый'}),/Реакция изменилась/);assert.equal(t.run('sequenceCapture.plan[0].roll_result'),'старый');
});
test('review commits all attacks once and only after the final button',async()=>{
 const t=setup();t.nodes['dialog-submit']={insertAdjacentHTML(){}};t.run("sequenceCapture={index:0,ability:{name:'Осколки'},root:{op:'ability.use',character:1,ability:7,sequence_revision:12},plan:[{target:1,roll_result:'17; 4'},{target:null,external_target:'<Гоблин>',roll_result:'20; 8'}]}");
 t.ctx.sequenceReview({characters:t.ctx.S.characters,inputs:{attack_sequence:{attacks:[{inputs:{}},{inputs:{}}]}}});assert.equal(t.ctx.writes.length,0);assert.match(t.ctx.html,/&lt;Гоблин>/);
 await t.save()();assert.equal(t.ctx.writes.length,1);assert.equal(t.ctx.writes[0].attacks.length,2);assert.equal(t.ctx.writes[0].sequence_revision,12);assert.equal(t.run('sequenceCapture'),null);assert.equal(t.run('sequenceCharacters'),null);
});
test('retrying an uncertain final response reuses the same operation key',async()=>{
 const t=setup();t.nodes['dialog-submit']={insertAdjacentHTML(){}};t.run("sequenceCapture={index:0,ability:{name:'Серия'},root:{character:1,ability:7},plan:[{target:1,roll_result:'17'}]}");
 const keys=[];t.ctx.api=async(payload,key)=>{keys.push(key);if(keys.length===1)throw Error('Нет связи');return {ok:true}};
 t.ctx.sequenceReview({characters:t.ctx.S.characters,inputs:{attack_sequence:{attacks:[{inputs:{}}]}}});const commit=t.save();
 await assert.rejects(commit,/Нет связи/);await commit();assert.deepEqual(keys,['series-key','series-key']);
});
test('choosing a spell in a series opens a composed draft without dropping the choice or saving',async()=>{
 const t=setup();t.run("sequenceCapture={index:0,root:{character:1,ability:7,sequence_revision:12},plan:[{target:2},{target:2}],forms:[]}");
 t.ctx.response.characters=[{id:1,abilities:[{id:9,weavable:true}]}];let bridge;t.ctx.sequenceSpell=b=>bridge=b;
 const result=await t.ctx.submitSequence({character:1,ability:7,targets:[2],outcome:'hit',roll_result:'18; 4',weave_ability:9});
 assert.equal(t.ctx.writes.length,0);assert.equal(t.ctx.request.body.completed,1);assert.equal(t.run('sequenceCapture.plan[0].roll_result'),undefined);
 result.next();assert.equal(bridge.spell.id,9);assert.equal(bridge.row.roll_result,'18; 4');assert.equal(bridge.attack.weave_ability,9);
});
test('ordinary woven spell is validated with its attack and only then advances the outer series',async()=>{
 const t=setup();t.run("sequenceCapture={index:0,root:{character:1,ability:7,sequence_revision:12},plan:[{target:2},{target:2}],forms:[]};sequenceBridge={outer:sequenceCapture,index:0,row:{target:2,outcome:'hit',roll_result:'18'},fields:[],spell:{id:9}}");
 await t.ctx.submitSequenceSpell({ability:9,targets:[2],roll_result:'6'});
 assert.equal(t.ctx.writes.length,0);assert.equal(t.ctx.request.body.attacks[0].weave.ability,9);assert.equal(t.run('sequenceCapture.plan[0].weave.roll_result'),'6');assert.equal(t.run('sequenceBridge'),null);
});
test('a spell series returns to the outer attack without committing a standalone event',async()=>{
 const t=setup();t.nodes['dialog-submit']={insertAdjacentHTML(){}};
 t.run("const outer={index:0,root:{character:1,ability:7,sequence_revision:12},plan:[{target:1},{target:1}],forms:[]};sequenceCapture={ability:{name:'Заклинание'},root:{character:1,ability:9,sequence_revision:12,weave_parent:{ability:7},before_sequence:{completed:0}},plan:[{target:1,roll_result:'19'}],returnBridge:{outer,index:0,row:{target:1,roll_result:'18'},fields:[]}};");
 t.ctx.sequenceReview({characters:t.ctx.S.characters,inputs:{attack_sequence:{attacks:[{inputs:{}}]}}});await t.save()();
 assert.equal(t.ctx.writes.length,0);assert.equal(t.ctx.request.body.ability,7);const child=t.ctx.request.body.attacks[0].weave;assert.equal(child.ability,9);assert.equal(child.attacks[0].roll_result,'19');assert.equal(child.before_sequence,undefined);assert.equal(child.weave_parent,undefined);
});
test('canceling a woven spell during preview cannot restore its abandoned outer draft',async()=>{
 const t=setup();t.run("sequenceCapture={root:{},plan:[{target:2}],forms:[]};sequenceBridge={outer:sequenceCapture,index:0,row:{target:2},fields:[],spell:{id:9}}");let finish;t.ctx.fetch=()=>new Promise(resolve=>finish=resolve);
 const pending=t.ctx.submitSequenceSpell({ability:9});t.ctx.clearSequence();finish({ok:true,json:async()=>t.ctx.response});await pending;
 assert.equal(t.run('sequenceCapture'),null);assert.equal(t.ctx.writes.length,0);
});
test('reload confirmation belongs to the chosen shot and is removed when unchecked',async()=>{
 const t=setup();t.run("sequenceCapture={index:1,root:{character:1,ability:7},plan:[{target:2,roll_result:'18'},{target:2}],forms:[]}");
 t.ctx.formObject=()=>({series_reload:'on'});await t.ctx.submitSequence({outcome:'hit',roll_result:'19'});assert.equal(t.ctx.request.body.attacks[1].reload_before,true);assert.equal(t.ctx.request.body.attacks[0].reload_before,undefined);
 t.ctx.formObject=()=>({});await t.ctx.submitSequence({outcome:'hit',roll_result:'19'});assert.equal(t.ctx.request.body.attacks[1].reload_before,undefined);assert.equal(t.ctx.writes.length,0);
});
test('reload prompt only appears for a discharged weapon attack',()=>{
 const t=setup(),c={calc:{needs_reload:true,reload_action:'minor'},runtime:{actions:{minor:1}}};
 assert.match(t.ctx.sequenceReload({data:{weapon:true}},c),/required/);assert.match(t.ctx.sequenceReload({data:{weapon:true}},c),/малое действие \(1\)/);
 assert.equal(t.ctx.sequenceReload({data:{damage:true}},c),'');c.calc.needs_reload=false;assert.equal(t.ctx.sequenceReload({data:{weapon:true}},c),'');
});
