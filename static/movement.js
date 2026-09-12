function movementForm(c){
 modal('Движение',`${selector('move_mode','Способ',[{id:'walk',name:'Обычное движение'},{id:'step',name:'Шаг'},...(c.runtime.effects||[]).some(e=>(e.status||e.name)==='Сбит с ног')?[{id:'stand',name:'Подняться на ноги'}]:[]],'walk')}<div id="movement-fields">${input('cell_cost','Стоимость одной клетки',1,'number','min="1" max="1000" step="1" required')}${input('cells','Пройти клеток',Math.max(1,c.calc.speed),'number','min="1" step="1" required')}</div><p id="movement-hint" class="notice"></p>`,async()=>{const f=formObject();return api(f.move_mode==='stand'?{op:'action.spend',character:c.id,action:'move',exchange:'stand'}:{op:'action.move',character:c.id,mode:f.move_mode,cells:Number(f.cells),cell_cost:Number(f.cell_cost)})},'Выполнить');updateMovementForm(true);
}
function updateMovementForm(reset=false){
 if(!el('movement-fields'))return;
 const c=current(),f=formObject(),stand=f.move_mode==='stand',step=f.move_mode==='step',cost=Number(f.cell_cost||1),limit=step?c.calc.step:Math.floor(c.calc.speed/cost);
 el('movement-fields').hidden=stand;
 const field=dialogBody.querySelector('[name="cells"]');field.disabled=stand;dialogBody.querySelector('[name="cell_cost"]').disabled=stand;field.max=Math.max(0,limit);
 if(reset)field.value=Math.max(1,limit);
 const immobilized=(c.runtime.effects||[]).some(e=>(e.status||e.name)==='Обездвижен');
 const error=!stand&&(immobilized?'Персонаж обездвижен':step&&cost!==1?'Шаг недоступен на клетке с повышенной стоимостью':limit<1?'Недостаточно скорости для одной клетки':'');
 el('movement-hint').textContent=error||(stand?'Действие движения: подняться на ноги':`До ${limit} клеток. ${step?'Не провоцирует атаки.':'Стоимость: '+cost+' за клетку.'}`);
 el('dialog-submit').disabled=!!error;
}
function movementLog(row){return row?'<br>'+esc((row.mode==='step'?'Шаг':'Движение')+': '+row.cells+' кл.'+(row.cell_cost>1?' · стоимость клетки '+row.cell_cost:'')+(row.mode==='step'?' · без провокации':'')):''}
document.addEventListener('change',e=>{if(e.target.name==='move_mode')updateMovementForm(true)});
document.addEventListener('input',e=>{if(e.target.name==='cell_cost')updateMovementForm()});
