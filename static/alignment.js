/* Geometry mirrors chapter 8; transition rules are supplied by the server. */
let alignmentMode='base';
const innerAngles={'Свобода':-90,'Хаос':-30,'Общее':30,'Необходимость':90,'Порядок':150,'Личное':210};
const outerAngles={'Решимость':-90,'Творчество':-60,'Интуиция':-30,'Равенство':0,'Альтруизм':30,'Коллектив':60,'Адаптация':90,'Закон':120,'Система':150,'Статус':180,'Эгоизм':210,'Независимость':240};
function alignmentPoint(angle,r){return {x:50+Math.cos(angle*Math.PI/180)*r,y:50+Math.sin(angle*Math.PI/180)*r}}
function alignmentOuterPoint(angle){return alignmentPoint(angle,[-90,90].includes(angle)?45:38)}
function alignmentForm(info){
 alignmentMode='base';
 return `<div id="alignment-editor">${[0,1,2].map(i=>`<input type="hidden" name="value${i}" value="${esc(info.alignment_values?.[i]||'')}">`).join('')}<input type="hidden" name="alignment_extra" value="${esc(info.alignment_extra||'')}">${[0,1].map(i=>`<input type="hidden" name="priority${i}" value="${esc(info.priorities?.[i]||'')}">`).join('')}<div class="alignment-toolbar">${btn('Основные ценности','alignment.mode','data-mode="base"')}${btn('+ Противоречие','alignment.mode','data-mode="extra"')}${btn('Убрать дополнительную','alignment.clear','id="alignment-clear"')}</div><p id="alignment-hint" class="muted"></p><div class="alignment-wheel" role="group" aria-label="Круг мировоззрения"><svg preserveAspectRatio="none" viewBox="0 0 100 100" aria-hidden="true" class="alignment-lines"></svg><span class="alignment-center" aria-hidden="true">✧</span>${Object.entries(innerAngles).map(([name,angle])=>{const p=alignmentPoint(angle,20);return btn(name,'alignment.value',`data-value="${name}" class="alignment-node inner" style="left:${p.x}%;top:${p.y}%" aria-pressed="false"`)}).join('')}${Object.entries(outerAngles).map(([name,angle])=>{const p=alignmentOuterPoint(angle);return btn(name,'alignment.priority',`data-value="${name}" class="alignment-node outer" style="left:${p.x}%;top:${p.y}%" aria-pressed="false"`)}).join('')}</div><p id="alignment-selection" class="alignment-selection"></p><div id="alignment-abilities"></div></div>`;
}
function alignmentState(){
 const f=formObject(),rules=S.rules.alignment;
 const values=[f.value0,f.value1,f.value2],extra=f.alignment_extra,selected=new Set([...values,extra].filter(Boolean));
 const joint=Object.entries(rules.joint).filter(([name,pair])=>pair.every(x=>selected.has(x)));
 const used=new Set(joint.flatMap(([name,pair])=>pair));
 const available=new Set([...joint.map(([name])=>name),...Object.entries(rules.dotted).filter(([name,value])=>selected.has(value)&&!used.has(value)).map(([name])=>name)]);
 const priorities=[f.priority0,f.priority1].map(id=>entry(id)).filter(Boolean);
 return {values,extra,selected,available,priorities};
}
function updateAlignment(clearUnavailable=false){
 const root=el('alignment-editor');if(!root)return;
 let state=alignmentState();
 if(clearUnavailable){
  if(state.values.includes(state.extra)){root.querySelector('[name=alignment_extra]').value='';state=alignmentState()}
  const kept=state.priorities.filter(x=>state.available.has(x.name));
  [0,1].forEach(i=>root.querySelector(`[name=priority${i}]`).value=kept[i]?.id||'');state=alignmentState();
 }
 const complete=state.values.every(Boolean);
 root.querySelectorAll('[data-do="alignment.mode"]').forEach(b=>{b.classList.toggle('active',b.dataset.mode===alignmentMode);b.setAttribute('aria-pressed',String(b.dataset.mode===alignmentMode));if(b.dataset.mode==='extra')b.disabled=!complete});
 el('alignment-clear').hidden=!state.extra;
 el('alignment-hint').textContent=alignmentMode==='extra'?'Выберите дополнительную ценность.':'Выберите по одной ценности из каждой пары, затем два приоритета.';
 root.querySelectorAll('[data-do="alignment.value"]').forEach(b=>{const name=b.dataset.value;b.classList.toggle('selected',state.selected.has(name));b.classList.toggle('extra',name===state.extra);b.setAttribute('aria-pressed',String(state.selected.has(name)));b.disabled=alignmentMode==='extra'&&state.values.includes(name);b.title=S.rules.alignment.pairs.find(pair=>pair.includes(name)).join(' / ')});
 root.querySelectorAll('[data-do="alignment.priority"]').forEach(b=>{const name=b.dataset.value,chosen=state.priorities.some(x=>x.name===name);b.disabled=!complete||!state.available.has(name);b.classList.toggle('available',complete&&state.available.has(name));b.classList.toggle('selected',chosen);b.setAttribute('aria-pressed',String(chosen));b.title=S.rules.alignment.joint[name]?.join(' + ')||`${S.rules.alignment.dotted[name]} без доступной сплошной связи`});
 root.querySelector('svg').innerHTML=[...Object.entries(S.rules.alignment.joint).flatMap(([name,pair])=>pair.map(value=>({name,value,dotted:false}))),...Object.entries(S.rules.alignment.dotted).map(([name,value])=>({name,value,dotted:true}))].map(({name,value,dotted})=>{const a=alignmentPoint(innerAngles[value],20),b=alignmentOuterPoint(outerAngles[name]);return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" class="${state.available.has(name)?'lit':''}" ${dotted?'stroke-dasharray="1 1"':''}/>`}).join('');
 el('alignment-selection').textContent=`Приоритеты ${state.priorities.length}/2: ${state.priorities.map(x=>x.name).join(' · ')||'выберите на внешнем круге'}`;
 const names=state.priorities.map(x=>x.name),choices=S.catalog.filter(e=>e.kind==='ability'&&e.data.source_name==='Приоритеты'&&names.includes(e.data.source_group));
 const learned=id=>dialogBody.querySelector(`#learned-list input[value="${id}"]`)?.checked;
 el('alignment-abilities').innerHTML=choices.length?`<div class="alignment-ability-groups">${[false,true].map(passive=>`<section><h4>${passive?'Пассивное':'Активное'} небоевое</h4>${choices.filter(e=>(e.data.keywords||[]).some(k=>k.startsWith('Пассив'))===passive).map(e=>`<details class="alignment-ability"><summary>${esc(e.name)}</summary><p>${esc(e.description)}</p>${btn(learned(e.id)?'Выбрано':'Выбрать','alignment.ability',`data-id="${e.id}" aria-pressed="${learned(e.id)}"`)}</details>`).join('')}</section>`).join('')}</div>`:'';
 if(el('learned-list'))filterLearned();
}
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-do^="alignment."]');if(!b||b.disabled)return;
 const root=el('alignment-editor'),action=b.dataset.do;let state=alignmentState();
 if(action==='alignment.mode')alignmentMode=b.dataset.mode;
 if(action==='alignment.clear'){root.querySelector('[name=alignment_extra]').value='';alignmentMode='base'}
 if(action==='alignment.value'){
  const value=b.dataset.value;
  if(alignmentMode==='extra')root.querySelector('[name=alignment_extra]').value=state.extra===value?'':value;
  else{const i=S.rules.alignment.pairs.findIndex(pair=>pair.includes(value));root.querySelector(`[name=value${i}]`).value=value}
 }
 if(action==='alignment.priority'){
  const name=b.dataset.value,record=S.catalog.find(x=>x.kind==='effect'&&x.data.priority&&x.name===name);if(!record)return;
  let chosen=state.priorities.map(x=>x.id);
  if(chosen.includes(record.id))chosen=chosen.filter(id=>id!==record.id);else if(chosen.length<2)chosen.push(record.id);else{toast('Снимите один из двух приоритетов');return}
  [0,1].forEach(i=>root.querySelector(`[name=priority${i}]`).value=chosen[i]||'');
 }
 if(action==='alignment.ability'){
  const a=entry(b.dataset.id),passive=(a.data.keywords||[]).some(k=>k.startsWith('Пассив'));
  const checked=dialogBody.querySelector(`#learned-list input[value="${a.id}"]`)?.checked;
  S.catalog.filter(x=>x.kind==='ability'&&x.data.source_name==='Приоритеты'&&(x.data.keywords||[]).some(k=>k.startsWith('Пассив'))===passive).forEach(x=>{const input=dialogBody.querySelector(`#learned-list input[value="${x.id}"]`);if(input)input.checked=x.id===a.id&&!checked});
 }
 updateAlignment(['alignment.value','alignment.clear'].includes(action));
});
