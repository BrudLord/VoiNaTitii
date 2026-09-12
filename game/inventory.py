"""Transactional inventory mutations, including reversible stock movements."""
import copy
import re
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from .models import Item, Character, Entry
from .rules import Change, current_scene
from . import enchantments, weaponry


def amount(value, maximum=100000, minimum=0):
    from .views import bounded
    if isinstance(value,bool) or isinstance(value,float) and not value.is_integer():
        raise ValueError('Количество должно быть целым')
    return bounded(value,minimum,maximum)


def new_item(change, character=None, campaign=None):
    item=Item.objects.create(character=character,campaign=campaign,name='',quantity=0,archived=True,revision=0)
    change.watch(item)
    item.archived=False
    return item


def equip_other_armor(change, item):
    if item.character_id and item.equipped and item.data.get('item_type')=='armor':
        for other in item.character.items.filter(equipped=True,archived=False).exclude(pk=item.pk):
            if other.data.get('item_type')=='armor':change.watch(other).equipped=False


def mutate(user,p):
    from .views import owned, access_campaign, master, validate_entry
    op=p['op']
    if op not in ['item.save','item.equip','item.transfer','item.consume','item.delete']:
        raise ValueError('Неизвестная операция с предметом')
    item=get_object_or_404(Item,pk=p['id'],archived=False) if p.get('id') else None
    if not item and op!='item.save':raise ValueError('Выберите предмет')
    if item:
        owned(user,item.character_id) if item.character_id else access_campaign(user,item.campaign_id)
        if 'revision' in p and p['revision']!=item.revision:
            raise ValueError('Предмет уже изменился. Обновите данные перед повтором операции.')
    character=item.character if item and item.character_id else None
    scene=current_scene(character) if character else None
    if scene and op in ['item.save','item.delete','item.transfer']:
        raise ValueError('Редактирование и передача предмета доступны после боя')
    label={'item.save':'Предмет','item.equip':'Экипировка','item.transfer':'Передача','item.consume':'Расход','item.delete':'Удаление'}[op]
    change=Change(user,label,scene)
    if item:change.watch(item)
    if op=='item.equip':
        if item.data.get('item_type') in ['currency','consumable','material']:raise ValueError('Этот предмет нельзя надеть')
        if not character:raise ValueError('Сначала передайте предмет персонажу')
        if not item.equipped and not item.quantity:raise ValueError('Нет предмета в наличии')
        change.watch(character)
        if scene:
            if item.data.get('item_type')=='armor':raise ValueError('Доспех меняется вне боя')
            if scene.state['order'][scene.state['turn']]!=character.id or character.runtime['actions'].get('main',0)<1:
                raise ValueError('Для смены оружия нужно основное действие в свой ход')
            character.runtime['actions']['main']-=1
        item.equipped=not item.equipped
        if item.equipped and item.data.get('dice'):character.runtime['weapon_id']=item.id
        if item.equipped and item.data.get('item_type')=='focus':character.runtime['focus_id']=item.id
        equip_other_armor(change,item)
    elif op=='item.delete':
        item.archived=True;item.equipped=False;item.quantity=0
    elif op=='item.consume':
        if scene and item.equipped:raise ValueError('Сначала снимите предмет')
        count=amount(p.get('quantity'),item.quantity,1)
        item.quantity-=count
        if not item.quantity:item.equipped=False
        change.inputs={'quantity':count,'reason':str(p.get('reason',''))[:500]}
    elif op=='item.transfer':
        count=amount(p.get('quantity',item.quantity),item.quantity,1)
        destination_character=None;destination_campaign=None
        if p.get('character'):
            destination_character=get_object_or_404(Character,pk=p['character'])
            if current_scene(destination_character):raise ValueError('Получатель сейчас участвует в бою')
            campaigns=[item.campaign_id] if item.campaign_id else list(character.memberships.values_list('campaign_id',flat=True))
            shares=destination_character.memberships.filter(campaign_id__in=campaigns).exists()
            if item.campaign_id and not shares:raise ValueError('Получатель не участвует в этой кампании')
            if destination_character.owner_id!=user.id and not master(user) and not shares:
                raise PermissionDenied('Передавать можно участникам общей кампании')
        else:
            destination_campaign=access_campaign(user,p['campaign'])
            if character and not character.memberships.filter(campaign=destination_campaign).exists():
                raise ValueError('Персонаж не участвует в этой кампании')
        if (item.character_id,item.campaign_id)==(destination_character.id if destination_character else None,destination_campaign.id if destination_campaign else None):
            raise ValueError('Предмет уже находится в этом инвентаре')
        change.inputs={'quantity':count,'from_character':item.character_id,'from_campaign':item.campaign_id,
                       'to_character':destination_character.id if destination_character else None,'to_campaign':destination_campaign.id if destination_campaign else None}
        if count==item.quantity:
            item.character=destination_character;item.campaign=destination_campaign;item.equipped=False
        else:
            item.quantity-=count
            target=new_item(change,destination_character,destination_campaign)
            target.name=item.name;target.entry_id=item.entry_id;target.data=copy.deepcopy(item.data);target.slot=item.slot;target.quantity=count
            change.inputs['received_item']=target.id
    else:
        if not item:
            character=owned(user,p['character']) if p.get('character') else None
            campaign=access_campaign(user,p['campaign']) if not character else None
            if character and current_scene(character):raise ValueError('Предметы добавляются после боя')
            item=new_item(change,character,campaign)
        name=str(p.get('name','')).strip()
        if not name or len(name)>160:raise ValueError('Укажите название до 160 символов')
        data=copy.deepcopy(p.get('data',{}))
        if not isinstance(data,dict):raise ValueError('Некорректные свойства')
        validate_entry(data)
        kind=data.get('item_type','other')
        if kind not in ['weapon','focus','armor','shield','consumable','currency','material','other']:raise ValueError('Неизвестный тип предмета')
        item.name=name;item.quantity=amount(p.get('quantity',1));item.slot=str(p.get('slot',''))[:40]
        item.equipped=bool(p.get('equipped')) and bool(item.character_id) and item.quantity>0
        if kind=='material':
            if data.get('material_kind') not in ['magic_dust','elemental','other']:raise ValueError('Выберите вид компонента')
            if data.get('material_kind')=='elemental':
                from .crafting import ELEMENTS
                if data.get('element') not in set(ELEMENTS.values()):raise ValueError('Выберите стихию компонента')
        if kind=='currency':item.name='Золото';item.slot='';data={'item_type':'currency'}
        if kind in ['currency','consumable','material']:item.equipped=False
        enchantments.validate(data)
        weaponry.validate(data)
        if kind=='weapon' and data.get('dice') and not re.fullmatch(r'[1-9]\d{0,2}[кd][1-9]\d{0,2}',data['dice']):
            raise ValueError('Урон оружия: количество и грани кубиков, например 1к6')
        if 'entry' in p:item.entry=get_object_or_404(Entry,pk=p['entry'],kind='item') if p['entry'] else None
        item.data=data
        equip_other_armor(change,item)
    change.label=label+' · '+item.name
    change.finish()
    return {'id':item.id,'revision':item.revision}
