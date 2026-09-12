const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context={S:{rules:{status_profiles:{БП:['target_hit',1],Шок:['status',1]}}},document:{addEventListener(){}},formObject:()=>({}),mysticArrowPayload:()=>({mystic_arrows:[]}),chargedArrowPayload:()=>({}),selectedChargedArrows:()=>[]};vm.createContext(context);
for(const file of ['static/reactions.js','static/targeting.js'])vm.runInContext(fs.readFileSync(file,'utf8'),context);
const ability={data:{keywords:['Ближний'],damage_from_bp:true},formula:'1к6',hit_scope:'weapon'};
test('Shock supplies the strongest BP, alongside independent hit bonuses',()=>{const target={id:1,calc:{effects:[{name:'Шок',stat:'status',value:3},{name:'БП',stat:'target_hit',value:2},{name:'Бонус',stat:'target_hit',value:1}]}};assert.equal(context.targetHitBonus(ability,target),4);assert.equal(context.targetDamageFormula(ability,target),'1к6 +3 [БП]')});
test('BP scope consistently limits hit and damage bonuses',()=>{const target={id:1,calc:{effects:[{status:'БП',stat:'target_hit',value:7,keyword:'Дальнобойный'},{status:'Шок',stat:'status',value:2}]}};assert.equal(context.targetHitBonus(ability,target),2);assert.equal(context.targetDamageFormula(ability,target),'1к6 +2 [БП]')});
test('shock name on an unrelated bonus is not an elemental status',()=>{const target={id:1,calc:{effects:[{name:'Шок',stat:'damage',value:9}]}};assert.equal(context.targetHitBonus(ability,target),0)});

test('automatic hits show damage without a fabricated numeric attack roll',()=>{context.esc=String;context.checks=()=>[];context.current=()=>({calc:{effects:[]}});const a={data:{automatic_hit:true},formula:'2к12',hit_bonus:7};const preview=context.attackTargetPreview(a);assert.match(preview,/автоматическое попадание/);assert.match(preview,/2к12/);assert.doesNotMatch(preview,/\+7/);const log=context.attackTargetLog([{name:'Цель',automatic_hit:true,hit:null,damage:'2к12'}]);assert.match(log,/автоматическое попадание/);assert.doesNotMatch(log,/null|\+0/)});

test('forced movement preview respects binding, equipment and misses',()=>{context.esc=String;context.formObject=()=>({});context.mysticArrowPayload=()=>({mystic_arrows:['shift']});const a={data:{},mystic_arrows:{options:[{id:'shift',movement:5}]}},t={id:1,calc:{effects:[],forced_movement_reduction:1}};assert.match(context.forcedMovementPreview(a,t),/Сдвиг 4 клеток/);t.calc.effects=[{status:'Обездвижен'}];assert.match(context.forcedMovementPreview(a,t),/невозможен/);t.calc.effects=[];a.data.effects=[{status:'Обездвижен'}];assert.match(context.forcedMovementPreview(a,t),/невозможен/);context.formObject=()=>({outcome:'miss'});assert.equal(context.forcedMovementPreview(a,t),'');context.formObject=()=>({});context.mysticArrowPayload=()=>({mystic_arrows:[]})});

test('half damage on miss divides the whole formula and journal keeps the entered result',()=>{
 context.esc=String;context.formObject=()=>({outcome:'miss',external_bp:3});
 const a={data:{miss_damage_divisor:2,damage_from_bp:true},formula:'3к6+2'};
 assert.equal(context.targetDamageFormula(a,null),'(3к6+2 +3 [БП]) / 2');
 const log=context.attackTargetLog([{name:'Цель',outcome:'miss',hit:4,damage:'(3к6+2) / 2',miss_damage:{incoming:17,divisor:2,remaining:8.5}}]);
 assert.match(log,/промах/);assert.match(log,/17 ÷ 2 = 8,5/);
 a.data.miss_damage_divisor=0;assert.equal(context.targetDamageFormula(a,null),'0');context.formObject=()=>({});
});
