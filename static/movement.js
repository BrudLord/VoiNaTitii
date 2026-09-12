function iceAreas(c){const scene=byId(S.scenes,c.scene_id);return (scene?.state.order||[]).map(id=>{const source=byId(S.characters,id),strength=Math.max(0,...(source.runtime.effects||[]).filter(e=>(e.status||e.name)==='Чистые льды').map(e=>Math.abs(e.value)));return {id,name:source.name,strength}}).filter(a=>a.strength>0)}
function icePathFields(c){const areas=iceAreas(c);return areas.length?`<details><summary>Чистые льды · участки пути</summary><p>Область Вокруг 1. В пересечениях укажите клетки один раз — у области с большей стоимостью.</p>${areas.map(a=>input('ice_cells:'+a.id,a.name+' · цена клетки '+a.strength,0,'number','min="0" step="1"')).join('')}</details>`:''}
function icePath(){return [...dialogBody.querySelectorAll('[name^="ice_cells:"]')].map(n=>({source:Number(n.name.split(':')[1]),cells:Number(n.value)})).filter(s=>s.cells!==0)}
function movementForm(c){
 modal('Движение',`${selector('move_mode','Способ',[{id:'walk',name:'Обычное движение'},{id:'step',name:'Шаг'},...(c.runtime.effects||[]).some(e=>(e.status||e.name)==='Сбит с ног')?[{id:'stand',name:'Подняться на ноги'}]:[]],'walk')}<div id="movement-fields">${input('cell_cost','Обычная стоимость клетки',1,'number','min="1" max="1000" step="1" required')}${input('cells','Пройти клеток',Math.max(1,c.calc.speed),'number','min="1" step="1" required')}${icePathFields(c)}</div><p id="movement-hint" class="notice"></p>`,async()=>{const f=formObject();return api(f.move_mode==='stand'?{op:'action.spend',character:c.id,action:'move',exchange:'stand'}:{op:'action.move',character:c.id,mode:f.move_mode,cells:Number(f.cells),cell_cost:Number(f.cell_cost),terrain:icePath()})},'Выполнить');updateMovementForm(true);
}
function updateMovementForm(reset=false){
 if(!el('movement-fields'))return;
 const c=current(),f=formObject(),stand=f.move_mode==='stand',step=f.move_mode==='step',cost=Number(f.cell_cost||1),areas=iceAreas(c),path=icePath(),zoneCells=path.reduce((n,s)=>n+s.cells,0),extra=path.reduce((n,s)=>n+s.cells*Math.max(0,(areas.find(a=>a.id===s.source)?.strength||1)-cost),0),limit=step?c.calc.step:Math.max(0,Math.floor((c.calc.speed-extra)/cost));
 el('movement-fields').hidden=stand;
 const field=dialogBody.querySelector('[name="cells"]');field.disabled=stand;dialogBody.querySelector('[name="cell_cost"]').disabled=stand;field.max=Math.max(0,limit);
 if(reset){field.value=Math.max(1,limit);f.cells=field.value}
 dialogBody.querySelectorAll('#movement-fields input').forEach(n=>n.disabled=stand);
 const immobilized=(c.runtime.effects||[]).some(e=>(e.status||e.name)==='Обездвижен');
 const error=!stand&&(immobilized?'Персонаж обездвижен':step&&(cost!==1||extra>0)?'Шаг недоступен на клетке с повышенной стоимостью':zoneCells>Number(f.cells)||zoneCells>limit?'Проверьте число клеток в областях и длину пути':limit<1?'Недостаточно скорости для одной клетки':'');
 el('movement-hint').textContent=error||(stand?'Действие движения: подняться на ноги':`До ${limit} клеток. ${step?'Не провоцирует атаки.':'Стоимость пути: '+(Number(f.cells)*cost+extra)+' из '+c.calc.speed+'.'}`);
 el('dialog-submit').disabled=!!error;
}
function movementLog(row){return row?'<br>'+esc((row.mode==='step'?'Шаг':'Движение')+': '+row.cells+' кл.'+(row.cell_cost>1?' · стоимость клетки '+row.cell_cost:'')+(row.terrain?.length?' · Чистые льды: '+row.terrain.map(s=>s.name+' — '+s.cells+' кл. × '+s.cell_cost).join('; ')+' · всего '+row.total_cost:'')+(row.mode==='step'?' · без провокации':'')):''}
document.addEventListener('change',e=>{if(e.target.name==='move_mode')updateMovementForm(true)});
document.addEventListener('input',e=>{if(['cell_cost','cells'].includes(e.target.name)||e.target.name.startsWith('ice_cells:'))updateMovementForm()});
