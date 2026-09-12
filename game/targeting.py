"""Attack totals before effects of the current attack are applied."""
from . import enchantments


def hit_bonus(character, ability, calc):
    value=enchantments.ability_bonus(calc,ability,'hit')
    value+=sum(p.get('hit',0) for p in enchantments.for_ability(calc,ability))
    if ability.data.get('weapon'):value+=calc['weapon_hit']
    if ability.data.get('system') and any(a.name=='Мистическая точность' and not a.archived for a in character.abilities.all()):
        value+=calc['mods'][calc['primary']]
    return value


def resolve(character,ability,calc,targets,payload):
    if not (ability.data.get('damage') or ability.data.get('weapon')):return []
    external=payload.get('external_bp',0)
    if type(external) is not int or not 0<=external<=1000:
        raise ValueError('БП противника должно быть целым числом от 0 до 1000')
    if targets and external:raise ValueError('БП выбранных персонажей берётся из их эффектов')
    from .rules import computed
    base=hit_bonus(character,ability,calc)
    result=[]
    for target in targets or [None]:
        bonus=enchantments.ability_bonus({**calc,'effects':computed(target)['effects']},ability,'target_hit') if target else external
        result.append({'id':target.pk if target else None,'name':target.name if target else 'Цель на игровом поле',
                       'hit':base+bonus,'target_bonus':bonus,
                       'armored_hit':base+bonus+calc['armored_hit'] if ability.data.get('weapon') and calc['armored_hit'] else None})
    return result
