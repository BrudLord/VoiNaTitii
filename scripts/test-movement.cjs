const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function setup(){
 const fields={cells:{value:'4'},cell_cost:{value:'1'},ice:{name:'ice_cells:2',value:'1'}};
 const elements={'movement-fields':{},'movement-hint':{},'dialog-submit':{}};
 const character={id:1,scene_id:1,calc:{speed:6,step:3},runtime:{effects:[]}};
 const ctx={mode:'walk',S:{characters:[character,{id:2,name:'Цель',runtime:{effects:[{status:'Чистые льды',value:3}]}}],scenes:[{id:1,state:{order:[1,2]}}]},current:()=>character,byId:(rows,id)=>rows.find(r=>r.id===id),el:id=>elements[id],document:{addEventListener(){}},dialogBody:{querySelector:s=>s.includes('cell_cost')?fields.cell_cost:fields.cells,querySelectorAll:s=>s.includes('ice_cells')?[fields.ice]:Object.values(fields)}};
 ctx.formObject=()=>({move_mode:ctx.mode,cells:fields.cells.value,cell_cost:fields.cell_cost.value});
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('static/movement.js','utf8'),ctx);
 return {ctx,fields,elements};
}
test('mixed ice path previews the total cost and prevents a step',()=>{
 const {ctx,fields,elements}=setup();ctx.updateMovementForm();
 assert.equal(fields.cells.max,4);assert.match(elements['movement-hint'].textContent,/Стоимость пути: 6 из 6/);
 ctx.mode='step';ctx.updateMovementForm(true);assert.equal(elements['dialog-submit'].disabled,true);assert.match(elements['movement-hint'].textContent,/Шаг недоступен/);
 fields.ice.value='0';ctx.updateMovementForm(true);assert.equal(elements['dialog-submit'].disabled,false);assert.equal(fields.cells.value,3);
});
test('ice path cannot contain more cells than the route',()=>{
 const {ctx,fields,elements}=setup();fields.cells.value='1';fields.ice.value='2';ctx.updateMovementForm();
 assert.equal(elements['dialog-submit'].disabled,true);assert.match(elements['movement-hint'].textContent,/Проверьте число клеток/);
 ctx.mode='stand';ctx.updateMovementForm();assert.equal(elements['dialog-submit'].disabled,false);assert.equal(fields.ice.disabled,true);
});
