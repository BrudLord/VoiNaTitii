const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/app.js'),'utf8');
const refreshCode=source.slice(source.indexOf('let refreshSequence='),source.indexOf('\nfunction navigate('));
const state=(revision,extra={})=>({revision,user:{id:1},characters:[],campaigns:[],catalog_revision:'book-1',catalog:[{id:1,name:'Книга'}],rules:{version:1},...extra});
function setup(initial=state(1)){
 const requests=[],connection={textContent:'',classList:{add(){},remove(){}}};
 const context=vm.createContext({URLSearchParams,structuredClone,S:initial,campaignId:1,characterId:null,draftUser:1,
  pendingRender:false,dialog:{open:false},document:{activeElement:{tagName:'DIV'}},
  el:()=>connection,render(){},syncFocusedNote(){},
  fetch:url=>new Promise((resolve,reject)=>requests.push({url,resolve:data=>resolve({ok:true,json:async()=>structuredClone(data)}),reject}))});
 vm.runInContext(refreshCode,context);
 return {context,requests,connection};
}
test('changed HP keeps cached reference book and force refresh sends its version',async()=>{
 const {context:c,requests:r}=setup();const original=c.S.catalog;
 const p=c.refresh(true);assert.match(r[0].url,/catalog_revision=book-1/);assert.doesNotMatch(r[0].url,/[?&]revision=/);
 const data=state(2,{characters:[{id:2,owner_id:1,runtime:{hp:9}}]});delete data.catalog;delete data.rules;
 r[0].resolve(data);await p;assert.equal(c.S.catalog,original);assert.equal(c.S.characters[0].runtime.hp,9);
});
test('late response cannot replace newer HP or catalogue',async()=>{
 const {context:c,requests:r}=setup();const old=c.refresh(),fresh=c.refresh(true);
 r[1].resolve(state(3,{catalog_revision:'book-2',catalog:[{name:'Новая книга'}]}));await fresh;
 r[0].resolve(state(2));await old;assert.equal(c.S.revision,3);assert.equal(c.S.catalog[0].name,'Новая книга');
});
test('older request with a newer state still wins over unchanged polling',async()=>{
 const {context:c,requests:r}=setup();const force=c.refresh(true),poll=c.refresh();
 r[1].resolve({revision:1,unchanged:true});await poll;
 r[0].resolve(state(2));await force;assert.equal(c.S.revision,2);
});
test('stale failed request does not hide a successful connection',async()=>{
 const {context:c,requests:r,connection}=setup();const old=c.refresh(),fresh=c.refresh();
 r[1].resolve(state(2));await fresh;r[0].reject(new Error('old timeout'));await old;
 assert.equal(connection.textContent,'Изменения синхронизированы');
});
test('full catalogue replacement and following compact update stay consistent',async()=>{
 const {context:c,requests:r}=setup();const first=c.refresh();r[0].resolve(state(2,{catalog_revision:'book-2',catalog:[{id:3}],rules:{version:2}}));await first;
 const next=c.refresh();assert.match(r[1].url,/catalog_revision=book-2/);
 const data=state(3,{catalog_revision:'book-2'});delete data.catalog;delete data.rules;r[1].resolve(data);await next;
 assert.equal(c.S.catalog[0].id,3);assert.equal(c.S.rules.version,2);
});
