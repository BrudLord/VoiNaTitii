"""Book-defined item improvements with a single reversible material transaction."""
import copy
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from .models import Entry, Item
from .rules import Change, current_scene
from .inventory import amount, new_item
from . import enchantments, weaponry

ELEMENTS={'Малое изначальное зачарование':'Изначальная',**{'Малое зачарование '+suffix:name for suffix,name in [('огня','Огонь'),('воды','Вода'),('земли','Земля'),('воздуха','Воздух'),('тьмы','Тьма'),('света','Свет'),('молнии','Молния'),('холода','Холод'),('природы','Природа')]}}
ALCHEMY={'Малое зелье лечения':'healing_potion','Малый яд':'poison','Масло точности':'accuracy_oil'}


def profile(entry):
    if entry.name in ALCHEMY:return {'craft':'Алхимик','kind':'production','product':ALCHEMY[entry.name],'hours':3}
    if enchantments.profile(entry):return {'craft':'Зачарователь','kind':'enchantment','dust':50,'element':ELEMENTS.get(entry.name,entry.data.get('element',''))}
    if weaponry.profile(entry):return {'craft':'Оружейник','kind':'upgrade',**weaponry.profile(entry)}


def catalogue():
    return [{'id':e.id,'name':e.name,**profile(e)} for e in Entry.objects.filter(archived=False) if profile(e)]


def apply(user,p):
    from .views import owned, access_campaign
    c=owned(user,p['character'])
    if current_scene(c):raise ValueError('Мастерская доступна вне боя')
    recipe=get_object_or_404(Entry,pk=p['recipe'],archived=False)
    spec=profile(recipe)
    if not spec:raise ValueError('Выберите рецепт улучшения')
    known=c.abilities.filter(pk=recipe.id).exists() or c.knowledge.filter(entry=recipe,kind='recipe',archived=False,**({} if c.owner_id==user.id else {'private':False})).exists()
    crafts=set(Entry.objects.filter(pk__in=c.info.get('craft_ids',[]),kind='craft').values_list('name',flat=True))
    crafts.add(str(c.info.get('craft','')))
    if not known or spec['craft'] not in crafts:raise ValueError('Выберите нужное ремесло и изучите рецепт')
    def stock(pk,revision):
        item=get_object_or_404(Item,pk=pk,archived=False)
        if item.character_id:
            if item.character_id!=c.id:raise PermissionDenied('Используйте свои вещи или общий запас кампании')
        else:
            access_campaign(user,item.campaign_id)
            if not c.memberships.filter(campaign_id=item.campaign_id).exists():raise PermissionDenied('Персонаж не участвует в этой кампании')
        if revision!=item.revision:raise ValueError('Запас изменился. Откройте мастерскую заново')
        return item
    production=spec['kind']=='production'
    if production and p.get('prepared') is not True:raise ValueError('Подтвердите три часа приготовления в игровом мире')
    target=None if production else stock(p['item'],p.get('item_revision'))
    if target and target.quantity<1:raise ValueError('Нет предмета для улучшения')
    field='enchantments' if spec['kind']=='enchantment' else 'upgrades'
    if target and recipe.id in target.data.get(field,[]):raise ValueError('Это улучшение уже есть на предмете')
    if spec['kind']=='enchantment':
        if target.data.get('item_type') not in enchantments.profile(recipe)['types']:raise ValueError('Чары не подходят к предмету')
    elif not production and not weaponry.compatible(target,spec):raise ValueError('Улучшение не подходит к этому оружию')
    rows=p.get('supplies',[])
    if not isinstance(rows,list) or len(rows)>30:raise ValueError('Проверьте список материалов')
    supplies=[];seen=set();dust=0;component=0
    for row in rows:
        if not isinstance(row,dict):raise ValueError('Проверьте материалы')
        item=stock(row.get('item'),row.get('revision'))
        if item.id in seen or target and item.id==target.id:raise ValueError('Материал указан дважды или совпадает с предметом')
        seen.add(item.id)
        count=amount(row.get('quantity'),item.quantity,1)
        if item.equipped:raise ValueError('Снимите предмет перед расходованием как материала')
        role=row.get('role','material')
        if role=='dust':
            if item.data.get('material_kind')!='magic_dust':raise ValueError('Выберите магическую пыль')
            dust+=count
        elif role=='component':
            if item.data.get('material_kind')!='elemental' or spec.get('element') and item.data.get('element')!=spec['element']:
                raise ValueError('Выберите компонент нужной стихии')
            component+=count
        elif role!='material':raise ValueError('Неизвестный вид материала')
        supplies.append((item,count,role))
    if spec['kind']=='enchantment' and (dust!=50 or component<1):raise ValueError('Для чар нужны 50 мер магической пыли и стихийный компонент')
    change=Change(user,'Мастерская · '+recipe.name+' · '+c.name,inputs={'character':c.id,'recipe':recipe.id,'supplies':rows})
    if target:change.watch(target)
    for item,count,role in supplies:
        change.watch(item).quantity-=count
    if production:
        result=new_item(change,c)
        result.name=recipe.name;result.quantity=1
        result.data={'item_type':'consumable','description':recipe.description,'alchemy':spec['product'],
                     'recipe_id':recipe.id,'maker_id':c.id,'preparation_hours':spec['hours']}
        change.inputs['preparation_hours']=spec['hours']
    elif target.quantity>1:
        target.quantity-=1
        result=new_item(change,target.character,target.campaign)
        result.name=target.name;result.entry_id=target.entry_id;result.data=copy.deepcopy(target.data);result.slot=target.slot;result.quantity=1
    else:result=target
    result.data=copy.deepcopy(result.data)
    if not production:result.data.setdefault(field,[]).append(recipe.id)
    change.inputs['result_item']=result.id
    change.finish()
    return {'id':result.id}
