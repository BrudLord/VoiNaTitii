"""Draw a carried throwing weapon as part of one reversible attack."""
import copy
import re
from django.shortcuts import get_object_or_404
from .models import Item


def selection(character, payload):
    if not isinstance(payload,dict) or set(payload)!={'item','revision','mode'}:
        raise ValueError('Выберите оружие и способ атаки')
    if type(payload['item']) is not int or type(payload['revision']) is not int:
        raise ValueError('Обновите выбранное оружие')
    if payload['mode'] not in ['melee','ranged']:
        raise ValueError('Выберите ближнюю атаку или бросок')
    item=get_object_or_404(Item,pk=payload['item'],character=character,archived=False,quantity__gt=0)
    if item.revision!=payload['revision']:raise ValueError('Предмет уже изменился. Выберите оружие заново.')
    if item.equipped or item.data.get('on_ground'):
        raise ValueError('Достать частью атаки можно оружие, которое лежит в сумке')
    if item.data.get('item_type')!='weapon' or not item.data.get('dice') or not any(re.fullmatch(r'Метательное(?: \d+)?',word) for word in item.data.get('keywords',[])):
        raise ValueError('Частью атаки можно достать только метательное оружие')
    return item


def preview(character,payload):
    item=selection(character,payload)
    character=copy.copy(character);character.runtime=copy.deepcopy(character.runtime)
    item.equipped=True
    character._equipped_override=list(character.items.filter(equipped=True,quantity__gt=0,archived=False).order_by('id'))+[item]
    character.runtime.update(weapon_id=item.pk,attack_mode=payload['mode'])
    return character


def apply(change,character,ability,payload):
    if not ability.data.get('weapon') or ability.data.get('aura') or ability.data.get('category','active')!='active':
        raise ValueError('Извлечение оружия нужно совместить с оружейной атакой')
    item=selection(character,payload)
    change.watch(character)
    change.watch(item).equipped=True
    # All validations and this temporary write run in the action's transaction.
    # The Change keeps the original snapshot for a single attack undo/redo.
    item.save(update_fields=['equipped'])
    character.runtime.update(weapon_id=item.pk,attack_mode=payload['mode'])
    change.inputs['draw_weapon']={'item':item.pk,'name':item.name,'mode':payload['mode']}
