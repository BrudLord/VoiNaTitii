/* Searchable, keyboard-accessible selectors; native select remains the form value. */
(()=>{
 let opened=null, serial=0;
 function label(select){return select.getAttribute('aria-label')||select.closest('label')?.childNodes[0]?.textContent?.trim()||'Выбор'}
 function sync(select){
  const wrap=select.parentElement;if(!wrap?.classList.contains('f-select'))return;
  const button=wrap.querySelector('.f-select-button');
  button.textContent=select.selectedOptions[0]?.textContent||'Выбрать';
  button.disabled=select.disabled;
  button.setAttribute('aria-label',label(select)+': '+button.textContent);
 }
 function enhance(select){
  if(select.classList.contains('custom-native')){sync(select);return}
  const wrap=document.createElement('span');wrap.className='f-select';
  select.parentNode.insertBefore(wrap,select);wrap.append(select);
  select.classList.add('custom-native');select.tabIndex=-1;select.setAttribute('aria-hidden','true');
  const button=document.createElement('button');button.type='button';button.className='f-select-button';
  button.setAttribute('role','combobox');button.setAttribute('aria-haspopup','listbox');button.setAttribute('aria-expanded','false');
  wrap.append(button);sync(select);
  button.addEventListener('click',()=>open(select,button));
  button.addEventListener('keydown',e=>{if(['ArrowDown','ArrowUp','Enter',' '].includes(e.key)){e.preventDefault();open(select,button)}});
 }
 function close(focus=false){if(!opened)return;const old=opened;opened=null;old.popup.remove();old.button.setAttribute('aria-expanded','false');if(focus&&old.button.isConnected)old.button.focus()}
 function open(select,button){
  if(opened?.select===select){close(true);return}close();
  const popup=document.createElement('div');popup.className='f-select-popup';popup.id='choice-'+(++serial);
  const search=document.createElement('input');search.type='search';search.placeholder='Поиск';search.setAttribute('aria-label','Поиск вариантов');search.autocomplete='off';
  const list=document.createElement('div');list.className='f-select-options';list.setAttribute('role','listbox');list.setAttribute('aria-label',label(select));
  popup.append(search,list);(select.closest('dialog')||document.body).append(popup);
  opened={select,button,popup,search,list,index:0,options:[]};button.setAttribute('aria-expanded','true');button.setAttribute('aria-controls',popup.id);
  function draw(){
   if(!opened||opened.select!==select)return;
   const state=opened;list.replaceChildren();state.options=[...select.options].filter(x=>!x.hidden&&x.textContent.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()));
   state.index=Math.max(0,state.options.findIndex(x=>x.selected));
   state.options.forEach((option,i)=>{const row=document.createElement('button');row.type='button';row.tabIndex=-1;row.textContent=option.textContent;row.className='f-select-option';row.setAttribute('role','option');row.setAttribute('aria-selected',String(option.selected));row.disabled=option.disabled;row.id=popup.id+'-'+i;row.addEventListener('click',()=>choose(i));list.append(row)});
   if(!state.options.length){const empty=document.createElement('p');empty.textContent='Нет вариантов';list.append(empty)}highlight();
  }
  function highlight(){if(!opened)return;[...list.children].forEach((x,i)=>x.classList.toggle('focused',i===opened.index));const row=list.children[opened.index];if(row){search.setAttribute('aria-activedescendant',row.id);row.scrollIntoView({block:'nearest'})}}
  function choose(index){const option=opened?.options[index];if(!option||option.disabled)return;select.value=option.value;sync(select);close(true);select.dispatchEvent(new Event('change',{bubbles:true}))}
  search.addEventListener('input',draw);
  popup.addEventListener('keydown',e=>{if(!opened)return;if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close(true)}else if(e.key==='Tab'){close()}else if(e.key==='Enter'){e.preventDefault();choose(opened.index)}else if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();const n=opened.options.length;if(n){opened.index=(opened.index+(e.key==='ArrowDown'?1:-1)+n)%n;highlight()}}});
  const rect=button.getBoundingClientRect(),width=Math.min(Math.max(rect.width,240),innerWidth-24);
  popup.style.width=width+'px';popup.style.left=Math.max(12,Math.min(rect.left,innerWidth-width-12))+'px';
  if(innerHeight-rect.bottom<240&&rect.top>250){popup.style.bottom=(innerHeight-rect.top+5)+'px';popup.style.maxHeight=Math.min(350,rect.top-20)+'px'}else{popup.style.top=(rect.bottom+5)+'px';popup.style.maxHeight=Math.max(120,Math.min(350,innerHeight-rect.bottom-17))+'px'}
  draw();search.focus();
 }
 document.addEventListener('pointerdown',e=>{if(opened&&!opened.popup.contains(e.target)&&!opened.button.contains(e.target))close()},true);
 document.addEventListener('change',e=>{if(e.target instanceof HTMLSelectElement)sync(e.target)});
 window.addEventListener('resize',()=>close());
 document.addEventListener('close',()=>close(),true);
 const observer=new MutationObserver(records=>{
  if(opened&&!opened.select.isConnected)close();
  for(const r of records){const select=r.target instanceof Element?r.target.closest('select'):r.target.parentElement?.closest('select');if(select)enhance(select);
   for(const node of r.addedNodes){if(!(node instanceof Element))continue;if(node.matches('select'))enhance(node);node.querySelectorAll('select').forEach(enhance)}
  }
 });
 document.querySelectorAll('select').forEach(enhance);observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','selected']});
})();
