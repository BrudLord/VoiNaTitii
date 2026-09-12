"""Attack totals before effects of the current attack are applied."""
from . import enchantments


def hit_bonus(character, ability, calc):
    value=enchantments.ability_bonus(calc,ability,'hit')+ability.data.get('attack_hit_bonus',0)
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
    prone=payload.get('external_prone',False)
    if type(prone) is not bool or (targets and prone):raise ValueError('Состояние выбранной цели берётся из её эффектов')
    from .weaponry import keywords, matches_keyword
    external+=2 if prone and matches_keyword('Ближний',keywords(ability,calc)) else 0
    from .rules import computed, formula
    from .statuses import status_name
    base=hit_bonus(character,ability,calc)
    result=[]
    for target in targets or [None]:
        effects=computed(target)['effects'] if target else []
        bp=max((max(0,e.get('value',0)) for e in effects if status_name(e)=='БП'),default=0) if target else payload.get('external_bp',0)
        extra=bp if ability.data.get('damage_from_bp') else 0
        damage=formula(character,ability,payload.get('outcome')=='critical',calc)
        bonus=enchantments.ability_bonus({**calc,'effects':effects},ability,'target_hit') if target else external
        result.append({'id':target.pk if target else None,'name':target.name if target else 'Цель на игровом поле',
                       'hit':base+bonus,'target_bonus':bonus,'bp_damage':extra,
                       'damage':damage+(f' +{extra} [БП]' if extra else ''),
                       'armored_hit':base+bonus+calc['armored_hit'] if ability.data.get('weapon') and calc['armored_hit'] else None})
    return result


def finalize(change):
    """Append selected hit-only arrow riders to the affected target's formula."""
    for key in ['mystic_arrows','charged_arrows']:
        value=change.inputs.get(key,{})
        if not value.get('hit'):continue
        for row in change.inputs.get('attack_targets',[]):
            if row['id'] not in value.get('target_ids',[]) and not (row['id'] is None and value.get('external_target')):continue
            for choice in value.get('choices',[]):
                bonus=choice.get('damage_contribution')
                if bonus:row['damage']+=f" +{bonus['value']} [{bonus['type']}]"
