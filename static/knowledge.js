let knowledgeTab='enchantment',knowledgeSearch='',knowledgeArchive='active';
const knowledgeKinds={enchantment:'Чары',recipe:'Рецепты',contact:'Контакты',lore:'Записи'};
function knowledgeView(c){
 const tabs=`<div class="tabs knowledge-tabs">${Object.entries(knowledgeKinds).map(([id,name])=>btn(name,'knowledge.tab',`data-tab="${id}" class="${knowledgeTab===id?'active':''}"`)).join('')}</div>`;
 if(knowledgeTab==='enchantment')return tabs+enchantmentKnowledge(c);
 return tabs+`<div class="toolbar"><input id="knowledge-search" type="search" aria-label="Поиск знаний" placeholder="Поиск по записям и меткам" value="${esc(knowledgeSearch)}"><select id="knowledge-archive" aria-label="Состояние записей">${options([{id:'active',name:'Текущие'},{id:'archived',name:'Архив'},{id:'all',name:'Все'}],knowledgeArchive,null)}</select>${c.editable?btn('+ Запись','knowledge.new','class="primary"'):''}</div><div id="knowledge-rows">${knowledgeRows(c)}</div>`;
}
function knowledgeRows(c){
 const query=knowledgeSearch.toLowerCase();
 const rows=(c.knowledge||[]).filter(r=>r.kind===knowledgeTab&&(knowledgeArchive==='all'||r.archived===(knowledgeArchive==='archived'))&&[r.title,r.body,r.location,r.details,...r.tags].join(' ').toLowerCase().includes(query));
 return rows.map(r=>`<article class="knowledge-row"><details><summary><span><strong>${esc(r.title)}</strong><small>${esc([r.location,r.details].filter(Boolean).join(' · '))}</small></span><span class="pill">${r.private?'Личное':'Всем'}${r.archived?' · Архив':''}</span></summary><div class="knowledge-body"><p class="description">${esc(r.body)}</p>${pills(r.tags)}${r.entry_id?`<p>${btn('Рецепт из книги','knowledge.source',`data-entry="${r.entry_id}"`)}</p>`:''}<div class="button-group">${c.editable?btn('Изменить','knowledge.edit',`data-id="${r.id}"`)+btn(r.archived?'Восстановить':'В архив','knowledge.archive',`data-id="${r.id}"`):''}</div></div></details></article>`).join('')||'<div class="empty">Записей пока нет.</div>';
}
function knowledgeForm(c,row=null){
 const kind=row?.kind||knowledgeTab,personal=c.owner_id===S.user.id;
 const recipes=S.catalog.filter(e=>e.kind==='ability'&&e.data.book_group==='craft');
 modal(row?'Изменить запись':'Новая запись',`${kind==='recipe'?selector('knowledge_entry','Рецепт из книги',recipes,row?.entry_id):''}<div class="fields">${input('knowledge_title',kind==='contact'?'Имя / организация':'Название',row?.title||'','text','required maxlength="160"')}${input('knowledge_location',kind==='recipe'?'Где изучено / источник':'Где',row?.location||'','text','maxlength="200"')}</div>${input('knowledge_details',kind==='contact'?'Роль / отношения':kind==='recipe'?'Ингредиенты / стоимость':'Кратко',row?.details||'','text','maxlength="1000"')}${textArea('knowledge_body',kind==='recipe'?'Приготовление и эффект':'Подробности',row?.body||'')}${input('knowledge_tags','Метки через запятую',(row?.tags||[]).join(', '))}${personal?`<label class="checks"><input type="checkbox" name="knowledge_private" ${row?.private!==false?'checked':''}>Личная запись — видна только вам</label>`:'<p class="muted">Запись будет видна всем игрокам в листе персонажа.</p>'}`,async()=>{
  const f=formObject();await api({op:'knowledge.save',id:row?.id,revision:row?.revision,character:c.id,kind,
   title:f.knowledge_title,location:f.knowledge_location,details:f.knowledge_details,body:f.knowledge_body,
   tags:f.knowledge_tags.split(',').map(s=>s.trim()).filter(Boolean),private:personal&&!!f.knowledge_private,entry:num(f.knowledge_entry)||null});
 });
}
document.addEventListener('input',e=>{if(e.target.id==='knowledge-search'){knowledgeSearch=e.target.value;el('knowledge-rows').innerHTML=knowledgeRows(current())}});
document.addEventListener('change',e=>{
 if(e.target.id==='knowledge-archive'){knowledgeArchive=e.target.value;el('knowledge-rows').innerHTML=knowledgeRows(current())}
 if(e.target.name==='knowledge_entry'){
  const source=entry(e.target.value);if(!source)return;
  dialogBody.querySelector('[name=knowledge_title]').value=source.name;
  dialogBody.querySelector('[name=knowledge_body]').value=source.description;
  dialogBody.querySelector('[name=knowledge_location]').value=source.data.source_name||'';
 }
});
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-do]');if(!b||!b.dataset.do.startsWith('knowledge.'))return;
 try{
 const action=b.dataset.do,c=current(),r=byId(c.knowledge||[],b.dataset.id);
 if(action==='knowledge.tab'){knowledgeTab=b.dataset.tab;knowledgeSearch='';knowledgeArchive='active';render()}
 if(action==='knowledge.new')knowledgeForm(c);
 if(action==='knowledge.edit')knowledgeForm(c,r);
 if(action==='knowledge.archive')await command({op:'knowledge.archive',id:r.id,revision:r.revision,archived:!r.archived});
 if(action==='knowledge.source'){const source=entry(b.dataset.entry);modal(source?.name||'Рецепт',`<div class="description">${esc(source?.description||'Источник больше недоступен')}</div>`,null)}
 }catch(err){toast(err.message)}
});
