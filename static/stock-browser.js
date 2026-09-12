const stockFilters=new Map();
function stockFilter(scope){if(!stockFilters.has(scope))stockFilters.set(scope,{query:'',type:'',place:''});return stockFilters.get(scope)}
function stockText(value){return String(value??'').toLocaleLowerCase('ru').replace(/ё/g,'е').trim()}
function stockSearchText(item){const d=item.data||{},charmNames=[...(d.enchantments||[]),...(d.upgrades||[])].map(id=>S.catalog.find(e=>e.id===id)?.name||'');return stockText([item.name,itemTypes[inferredItemType(item)],item.slot,d.description,d.element,d.dice,d.crit?'Крит '+d.crit:'',d.armor?'КД '+d.armor:'',d.needs_reload?'Требует перезарядки':'',d.accuracy_oil?'Масло точности':'',...(d.keywords||[]),...(d.families||[]),...(d.effects||[]).map(e=>e.name||''),...charmNames].join(' '))}
function stockMatches(item,filter,personal=true){
 if(filter.type&&inferredItemType(item)!==filter.type)return false;
 const place=item.equipped?'equipped':item.data?.on_ground?'field':'bag';
 if(personal&&filter.place&&place!==filter.place)return false;
 const words=stockText(filter.query).split(/\s+/).filter(Boolean),text=stockSearchText(item);
 return words.every(word=>text.includes(word));
}
function stockOwner(scope){const [kind,id]=scope.split(':');return byId(kind==='character'?S.characters:S.campaigns,id)}
function stockResults(owner,scope){
 const personal=scope.startsWith('character:'),filter=stockFilter(scope),rows=owner.items.filter(item=>stockMatches(item,filter,personal));
 const active=!!(filter.query||filter.type||personal&&filter.place);
 let body='';
 if(!rows.length)body='<div class="empty">'+(owner.items.length?'Ничего не найдено. Измените условия поиска.':personal?'Инвентарь пуст':'Общий запас пуст')+'</div>';
 else if(personal){for(const [place,title] of [['equipped','Надето'],['bag','С собой'],['field','На поле']]){const group=rows.filter(i=>(i.equipped?'equipped':i.data.on_ground?'field':'bag')===place);if(group.length)body+='<section class="stock-group">'+(place==='bag'&&group.length===rows.length?'':'<h3>'+title+'</h3>')+group.map(i=>itemRow(i,owner.id)).join('')+'</section>'}}
 else body=rows.map(i=>itemRow(i,null,owner.id)).join('');
 return `<div class="stock-result-count muted" role="status">${active?'Найдено: '+rows.length+' из '+owner.items.length:''}</div>${body}`;
}
function stockBrowser(owner,kind){
 const scope=kind+':'+owner.id,filter=stockFilter(scope),personal=kind==='character',active=!!(filter.query||filter.type||personal&&filter.place);
 return `<div class="stock-browser" data-stock-scope="${scope}"><div class="stock-filters"><input type="search" data-stock-search aria-label="Найти предмет" placeholder="Название, свойство, зачарование" value="${esc(filter.query)}"><select data-stock-filter="type" aria-label="Тип предмета">${options(Object.entries(itemTypes).map(([id,name])=>({id,name})),filter.type,'Все типы')}</select>${personal?`<select data-stock-filter="place" aria-label="Расположение">${options([{id:'equipped',name:'Надето'},{id:'bag',name:'В сумке'},{id:'field',name:'На поле'}],filter.place,'Везде')}</select>`:''}<button type="button" data-stock-reset ${active?'':'hidden'}>Сбросить</button></div><div class="stock-results">${stockResults(owner,scope)}</div></div>`;
}
function updateStockBrowser(root){const scope=root.dataset.stockScope,owner=stockOwner(scope);if(!owner)return;const filter=stockFilter(scope);root.querySelector('.stock-results').innerHTML=stockResults(owner,scope);root.querySelector('[data-stock-reset]').hidden=!(filter.query||filter.type||scope.startsWith('character:')&&filter.place)}
document.addEventListener('input',e=>{if(!e.target.matches('[data-stock-search]'))return;const root=e.target.closest('[data-stock-scope]');stockFilter(root.dataset.stockScope).query=e.target.value;updateStockBrowser(root)});
document.addEventListener('change',e=>{if(!e.target.matches('[data-stock-filter]'))return;const root=e.target.closest('[data-stock-scope]');stockFilter(root.dataset.stockScope)[e.target.dataset.stockFilter]=e.target.value;updateStockBrowser(root)});
document.addEventListener('click',e=>{const button=e.target.closest('[data-stock-reset]');if(!button)return;const scope=button.closest('[data-stock-scope]').dataset.stockScope;stockFilters.delete(scope);render();document.querySelector('[data-stock-search]')?.focus()});
