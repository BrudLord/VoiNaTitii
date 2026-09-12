"""Attack totals before effects of the current attack are applied."""
import re
from . import enchantments, outcomes


def physical_weapon_units(ability,calc):
    """Only physical weapon terms; elemental riders never increase this coefficient."""
    d=ability.data
    if not d.get('weapon') or calc.get('unarmed') and not calc.get('unarmed_dice'):return 0
    formula=d.get('formula','')
    if d.get('damage_type'):
        return sum(int(n) for n in re.findall(r'(\d+)\s*Ор',formula)) if d['damage_type']=='Физический' else 0
    if d.get('system') or ability.name in ['Стандартная атака','Провоцированная атака']:
        return sum(int(n) for n in re.findall(r'(\d+)\s*Ор',formula))
    # Match the selected formula, so a conditional alternative in the description
    # cannot silently increase damage in the base attack.
    terms=re.findall(r'(\d+)\s*Ор(?:\s*[+−-]\s*(?:\d+\s*\*?\s*)?Мод)?\s+Физического урона',ability.description,re.I)
    units=sum(int(n) for n in re.findall(r'(\d+)\s*Ор',formula))
    return units if str(units) in terms else 0


def roll_conditions(ability,calc):
    from .statuses import status_name
    if ability.data.get('category','active')!='active' or not (ability.data.get('weapon') or ability.data.get('damage')) or ability.data.get('automatic_hit'):
        return []
    return ['Помеха на попадание: Ослепление'] if any(status_name(e)=='Ослепление' for e in calc['effects']) else []


def hit_bonus(character, ability, calc):
    value=enchantments.ability_bonus(calc,ability,'hit')+ability.data.get('attack_hit_bonus',0)
    value+=sum(p.get('hit',0) for p in enchantments.for_ability(calc,ability))
    if ability.data.get('weapon'):value+=calc['weapon_hit']
    if ability.data.get('system') and any(a.name=='Мистическая точность' and not a.archived for a in character.abilities.all()):
        value+=calc['mods'][calc['primary']]
    return value


def advantage(effects,ability,calc):
    from .statuses import status_name
    candidates=[{**e,'stat':'target_hit'} for e in effects if status_name(e) in ['БП','Шок']]
    return max((enchantments.ability_bonus({**calc,'effects':[e]},ability,'target_hit') for e in candidates),default=0,)


def target_hit_bonus(effects,ability,calc):
    from .statuses import status_name
    other=[e for e in effects if status_name(e) not in ['БП','Шок']]
    return max(0,advantage(effects,ability,calc))+enchantments.ability_bonus({**calc,'effects':other},ability,'target_hit')


def resolve(character,ability,calc,targets,payload):
    if not (ability.data.get('damage') or ability.data.get('weapon')):return []
    conductor=payload.get('external_conductor',0)
    if type(conductor) is not int or not 0<=conductor<=1000 or (targets and conductor):
        raise ValueError('Сила Сверхпроводника выбранной цели берётся из её эффектов')
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
    marks=[e for e in calc['effects'] if status_name(e)=='Метка']
    included=payload.get('mark_source_included',False)
    if type(included) is not bool:raise ValueError('Укажите, включён ли источник метки в атаку')
    selected={t.pk for t in targets}
    penalty=-3 if any(e.get('source_id') not in selected if e.get('source_id') else not included for e in marks) else 0
    automatic=bool(ability.data.get('automatic_hit'))
    if automatic:penalty=0
    base=hit_bonus(character,ability,calc)+penalty
    result=[]
    for target in targets or [None]:
        effects=computed(target)['effects'] if target else []
        bp=max(0,advantage(effects,ability,calc)) if target else payload.get('external_bp',0)
        extra=bp if ability.data.get('damage_from_bp') else 0
        strength=max((abs(e.get('value',0)) for e in effects if status_name(e)=='Сверхпроводник'),default=0) if target else conductor
        conductor_bonus=strength*physical_weapon_units(ability,calc)/2
        outcome=outcomes.for_target(payload,target.pk if target else 0)
        damage=formula(character,ability,outcome=='critical',calc)
        bonus=0 if automatic else target_hit_bonus(effects,ability,calc) if target else external
        result.append({'outcome':outcome,'id':target.pk if target else None,'name':target.name if target else 'Цель на игровом поле',
                       'automatic_hit':automatic,'hit':None if automatic else base+bonus,'roll_conditions':roll_conditions(ability,calc),'mark_penalty':penalty,'target_bonus':bonus,'bp_damage':extra,'conductor_damage':conductor_bonus,
                       'damage':damage+(f' +{extra} [БП]' if extra else '')+(f' +{conductor_bonus:g} [Сверхпроводник]' if conductor_bonus else ''),
                       'armored_hit':base+bonus+calc['armored_hit'] if not automatic and ability.data.get('weapon') and calc['armored_hit'] else None})
    divisor=ability.data.get('miss_damage_divisor',0)
    values=payload.get('miss_damage',{})
    if any(row['outcome']=='miss' for row in result) and divisor:
        keys={str(row['id'] or 0) for row in result if row['outcome']=='miss'}
        if not isinstance(values,dict) or set(values)!=keys or any(type(v) not in [int,float] or not 0<=v<=100000 for v in values.values()):
            raise ValueError('Введите урон до деления для каждой цели: число от 0 до 100000')
    for row in result:
        if row['outcome']=='miss':
            row['damage_before_miss']=row['damage']
            row['damage']='('+row['damage']+') / '+str(divisor) if divisor else '0'
            if divisor:
                incoming=values[str(row['id'] or 0)]
                row['miss_damage']={'incoming':incoming,'divisor':divisor,'remaining':incoming/divisor}
    return result


def finalize(change):
    """Append selected hit-only arrow riders to the affected target's formula."""
    for key in ['mystic_arrows','charged_arrows']:
        value=change.inputs.get(key,{})
        if not value.get('hit'):continue
        for row in change.inputs.get('attack_targets',[]):
            if row.get('outcome')=='miss':continue
            if row['id'] not in value.get('target_ids',[]) and not (row['id'] is None and value.get('external_target')):continue
            for choice in value.get('choices',[]):
                bonus=choice.get('damage_contribution')
                if bonus:row['damage']+=f" +{bonus['value']} [{bonus['type']}]"
