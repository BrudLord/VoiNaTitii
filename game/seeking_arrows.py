"""Repeat a missed standard attack against a different physical target."""
import copy
from .passives import turn_token

NAME = 'Ищущие стрелы'


def effective(ability):
    if ability.name != NAME:
        return ability
    from .models import Entry
    standard = Entry.objects.filter(kind='ability', name='Стандартная атака', archived=False).first()
    result = copy.copy(ability)
    result.data = {**(standard.data if standard else {'system': True, 'weapon': True, 'damage': True, 'formula': '1Ор + Мод'}),
                   'circle': ability.data.get('circle', 2), 'action': 'minor', 'category': 'active',
                   'manual': False, 'seeking': True, 'target': 'single', 'display_name':ability.display_name}
    return result


def reason(character, scene, calc):
    previous = character.runtime.get('missed_standard')
    if not previous or previous['turn'] != turn_token(scene):
        return 'Сначала промахнитесь стандартной атакой в этом ходу'
    if previous['weapon'] != calc['weapon_id'] or previous['mode'] != calc['attack_mode']:
        return 'Повторите атаку тем же оружием и способом'
    return ''


def validate(character, ability, payload, ids):
    if ability.name != NAME:
        return
    previous = character.runtime['missed_standard']
    if len(ids) > 1 or any(pk in previous['targets'] for pk in ids):
        raise ValueError('Выберите другую цель для повторной атаки')
    if not ids and not previous['targets'] and payload.get('different_target') is not True:
        raise ValueError('Подтвердите, что повторная атака направлена на другого противника в пределах дистанции')


def record(change, character, ability, scene, calc, payload, ids):
    if not (ability.data.get('weapon') or ability.data.get('damage')):
        return
    character.runtime.pop('missed_standard', None)
    if ability.name == NAME:
        change.inputs['seeking_arrow'] = {'different_external_target': payload.get('different_target') is True}
    if (ability.name in ['Стандартная атака', NAME]) and payload.get('outcome') == 'miss':
        character.runtime['missed_standard'] = {'turn': turn_token(scene), 'weapon': calc['weapon_id'],
                                              'mode': calc['attack_mode'], 'targets': ids}
