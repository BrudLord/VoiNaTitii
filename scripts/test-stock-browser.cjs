const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function setup(){
 const items=[{id:1,name:'Золото',quantity:50,data:{}},{id:2,name:'Копьё',quantity:2,equipped:true,data:{item_type:'weapon',dice:'1к8',keywords:['Двуручное'],enchantments:[10]}},{id:3,name:'Зелье',quantity:0,data:{item_type:'consumable',description:'Восстановление сил'}},{id:4,name:'Кинжал',quantity:1,data:{item_type:'weapon',on_ground:true,keywords:['Лёгкое'],upgrades:[11],needs_reload:true}}];
 const listeners={},owner={id:1,items},context={S:{catalog:[{id:10,name:'Малое зачарование огня'},{id:11,name:'Сбалансированный'}],characters:[owner],campaigns:[{id:1,items:[]}]},itemTypes:{currency:'Золото',weapon:'Оружие',consumable:'Расходник',other:'Прочее'},inferredItemType:i=>i.data.item_type||(i.name==='Золото'?'currency':i.data.dice?'weapon':'other'),byId:(rows,id)=>rows.find(x=>x.id===Number(id)),esc:s=>String(s).replace(/"/g,'&quot;'),options:()=>'',itemRow:(i,char,camp)=>`<article>${i.name}:${char||''}:${camp||''}</article>`,document:{addEventListener:(event,fn)=>{listeners[event]=fn}},render:()=>{}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/stock-browser.js','utf8'),context);return {context,items,owner,listeners};
}
test('search matches case, ё/е, enchantments, upgrades and several words',()=>{
 const {context,items}=setup();
 assert.equal(context.stockMatches(items[1],{query:'КОПЬЕ огн'}),true);
 assert.equal(context.stockMatches(items[3],{query:'легкое сбаланс'}),true);
 assert.equal(context.stockMatches(items[3],{query:'перезарядки'}),true);
 assert.equal(context.stockMatches(items[1],{query:'огн зелье'}),false);
});
test('type and location intersect without losing zero quantities or legacy currency',()=>{
 const {context,items}=setup();
 assert.equal(context.stockMatches(items[0],{type:'currency',place:'bag'}),true);
 assert.equal(context.stockMatches(items[2],{type:'consumable'}),true);
 assert.equal(context.stockMatches(items[3],{type:'weapon',place:'field'}),true);
 assert.equal(context.stockMatches(items[1],{type:'weapon',place:'field'}),false);
 assert.equal(context.stockMatches(items[1],{place:'field'},false),true);
});
test('each character and campaign keeps an independent filter',()=>{
 const {context}=setup();context.stockFilter('character:1').query='копье';context.stockFilter('character:2').type='weapon';
 assert.equal(context.stockFilter('campaign:1').query,'');assert.equal(context.stockFilter('character:1').type,'');
 assert.equal(context.stockFilter('character:1').query,'копье');
});
test('filtered groups and counts retain original ownership and items',()=>{
 const {context,items,owner}=setup(),before=JSON.stringify(items);
 context.stockFilter('character:1').place='field';let html=context.stockResults(owner,'character:1');
 assert.match(html,/Найдено: 1 из 4/);assert.match(html,/На поле/);assert.match(html,/Кинжал:1:/);assert.doesNotMatch(html,/Копьё/);
 context.stockFilter('campaign:1').type='weapon';html=context.stockResults(owner,'campaign:1');assert.match(html,/Копьё::1/);
 assert.equal(JSON.stringify(items),before);
});
test('no matches are distinct from empty inventory and reset remains available',()=>{
 const {context,owner}=setup();context.stockFilter('character:1').query='несуществующий';
 assert.match(context.stockBrowser(owner,'character'),/Ничего не найдено/);
 assert.match(context.stockBrowser(owner,'character'),/data-stock-reset >/);
 assert.match(context.stockResults({id:2,items:[]},'campaign:2'),/Общий запас пуст/);
});
test('typing updates only results and reads fresh synchronized stock',()=>{
 const {context,owner,listeners}=setup(),results={innerHTML:''},reset={},root={dataset:{stockScope:'character:1'},querySelector:s=>s==='.stock-results'?results:reset};
 const input={matches:()=>true,closest:()=>root,value:'копье'};listeners.input({target:input});assert.match(results.innerHTML,/Копьё/);
 owner.items=owner.items.filter(i=>i.id!==2);listeners.input({target:input});assert.match(results.innerHTML,/Ничего не найдено/);
 assert.equal(input.value,'копье');assert.equal(reset.hidden,false);
});
