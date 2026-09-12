const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const profile={Поджог:['status',1],Влага:['status',1],Кислота:['ac',-1],Шок:['status',1],Мороз:['speed',-1],Яд:['status',1],Благословение:['hit',1],Проклятье:['hit',-1],Насыщение:['status',1],Рассеивание:['status',1]};
const ctx={S:{rules:{status_profiles:profile,neutral:[['Поджог','Влага']],constructive:[['Влага','Шок','Оцепенение'],['Проклятье','Шок','Проклятый разряд']]}}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('static/reactions.js','utf8'),ctx);
const run=(old,effects,choices={})=>JSON.parse(JSON.stringify(ctx.reactionSequence({runtime:{effects:old}},effects,choices)));
test('later effect reacts with the newly applied status',()=>{const r=run([],[{name:'Влага',stat:'status',value:2,index:0},{name:'Шок',stat:'status',value:3,index:1}]);assert.equal(r.length,1);assert.equal(r[0].index,1);assert.equal(r[0].choices[0].id,'status:Влага');assert.equal(r[0].choices[0].strength,5)});
test('consumed status is unavailable to later effects',()=>{const old=[{key:'burn',name:'Поджог',stat:'status',value:2}];const effects=[{name:'Влага',stat:'status',value:2,index:0},{name:'Шок',stat:'status',value:3,index:1}];assert.equal(run(old,effects,{0:'burn'}).length,1);assert.equal(old.length,1)});
test('wait for selection before forecasting dependent effects',()=>{const r=run([{key:'curse',name:'Проклятье',stat:'hit',value:-2}],[{name:'Шок',stat:'status',value:3,index:0},{name:'Шок',stat:'status',value:4,index:1}]);assert.equal(r.length,1);assert.equal(r[0].choices[0].strength,5)});
test('saturation changes the strength of a subsequent discharge',()=>{const r=run([{key:'curse',name:'Проклятье',stat:'hit',value:-2}],[{name:'Насыщение',stat:'status',value:3,index:0},{name:'Шок',stat:'status',value:4,index:1}],{0:'curse'});assert.equal(r[1].choices[0].strength,9)});
test('non-status name collisions and manual effects do not trigger reactions',()=>{const r=run([{key:'bonus',name:'Проклятье',stat:'damage',value:-2}],[{name:'Проклятье',stat:'hit',value:-3,index:0,manual:true},{name:'Шок',stat:'status',value:4,index:1}]);assert.equal(r.length,0)});

test('dispersion radius is independent of spread effect strength and removal affects later reactions',()=>{
 const old=[{key:'burn',name:'Поджог',stat:'status',value:4}], effects=[{name:'Рассеивание',stat:'status',value:2,index:0},{name:'Влага',stat:'status',value:1,index:1}];
 const r=run(old,effects,{0:'burn'});assert.equal(r[0].choices[0].strength,2);assert.equal(r[0].choices[0].effect.value,4);assert.equal(r.length,2);
 assert.equal(ctx.reactionSequence({runtime:{effects:old}},effects,{0:'burn'},{0:{remove_source:true}}).length,1);
});

test('dispersion updates later primary targets in the shared preview',()=>{
 const world={1:{id:1,runtime:{effects:[{key:'burn',name:'Поджог',stat:'status',value:4}]}},2:{id:2,runtime:{effects:[]}}};
 const effects=[{name:'Рассеивание',stat:'status',value:2,index:0}];
 ctx.reactionSequence(world[1],effects,{0:'burn'},{0:{targets:[2]}},world);
 const rows=ctx.reactionSequence(world[2],effects,{}, {},world);
 assert.equal(rows[0].choices[0].effect.value,4);assert.equal(rows[0].choices[0].id,'status:Поджог');
});
