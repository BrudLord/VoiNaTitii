"""Applying prepared consumables without losing the item transaction history."""
import copy
from types import SimpleNamespace
from django.shortcuts import get_object_or_404
from .models import Item
from .rules import Change, current_scene, availability, computed
from .inventory import new_item


def apply_oil(user,p):
    from .views import owned
    c=owned(user,p['character'])
    oil=get_object_or_404(Item,pk=p['id'],character=c,archived=False)
    weapon=get_object_or_404(Item,pk=p['weapon'],character=c,archived=False)
    if oil.revision!=p.get('revision') or weapon.revision!=p.get('weapon_revision'):
        raise ValueError('Предметы изменились. Откройте форму заново')
    if oil.data.get('item_type')!='consumable' or not (oil.data.get('alchemy')=='accuracy_oil' or oil.name=='Масло точности'):
        raise ValueError('Выберите масло точности')
    if oil.quantity<1 or weapon.quantity<1:raise ValueError('Нет предмета в наличии')
    if weapon.data.get('item_type')!='weapon':raise ValueError('Масло наносится на оружие')
    if weapon.data.get('accuracy_oil'):raise ValueError('На это оружие уже нанесено масло')
    scene=current_scene(c)
    if scene:
        reason=availability(c,SimpleNamespace(data={'action':'main'},id=0),scene)
        if reason:raise ValueError(reason)
    change=Change(user,'Масло точности · '+weapon.name,scene,inputs={'character':c.id,'oil':oil.id,'weapon':weapon.id})
    change.watch(oil).quantity-=1
    change.watch(weapon)
    if scene:
        change.watch(c).runtime['actions']['main']-=1
        change.action(c,'main')
    if weapon.quantity>1:
        weapon.quantity-=1
        result=new_item(change,c)
        result.name=weapon.name;result.entry_id=weapon.entry_id;result.data=copy.deepcopy(weapon.data)
        result.quantity=1;result.slot=weapon.slot;result.equipped=weapon.equipped
        if weapon.equipped:
            selected=computed(c)['weapon_id']
            weapon.equipped=False
            if selected==weapon.id:change.watch(c).runtime['weapon_id']=result.id
    else:result=weapon
    result.data=copy.deepcopy(result.data)
    result.data['accuracy_oil']=True
    change.inputs['result_item']=result.id
    change.finish()
    return {'id':result.id}


def end_battle(change,character):
    for item in character.items.filter(archived=False):
        if item.data.get('accuracy_oil'):
            change.watch(item)
            item.data=copy.deepcopy(item.data)
            del item.data['accuracy_oil']
