"""Book 3186–3212: bow attack riders and cumulative mana exhaustion."""
from .rules import computed, put_effect
from .statuses import apply_status


OPTIONS = [
    {'id':'frost','name':'Морозная стрела','description':'Мороз 3 · три хода цели',
     'effect':{'status':'Мороз','stat':'speed','value':-3,'turns':3}},
    {'id':'shift','name':'Силовая стрела','description':'Сдвиг 5 · переместите цель на поле',
     'movement':5},
    {'id':'bind','name':'Приковывающая стрела','description':'Обездвижен · один ход цели',
     'effect':{'status':'Обездвижен','stat':'status','value':1,'turns':1}},
    {'id':'stun','name':'Оглушающая стрела','description':'Оглушение 2 · пропустить два действия',
     'effect':{'status':'Оглушение','stat':'status','value':2,'duration':'actions'}},
    {'id':'vulnerable','name':'Порченная стрела','description':'Уязвимость 1 всем типам урона · один ход цели',
     'effect':{'status':'Уязвимость','stat':'status','value':1,'turns':1,
               'note':'На 1 больше урона от любого источника; ХП изменяет мастер.'}},
]


def profile(character, ability, calc):
    learned={a.name for a in character.abilities.all() if not a.archived}
    if 'Мистические стрелы' not in learned or not ability.data.get('system') or not ability.data.get('weapon'):
        return None
    weapon=next((i for i in character.items.all() if i.pk==calc['weapon_id']),None)
    if not weapon or 'Луки' not in weapon.data.get('families',weapon.data.get('keywords',[])):
        return None
    options=[dict(o) for o in OPTIONS]
    if 'Глыба' in learned:
        stun=next(o for o in options if o['id']=='stun')
        stun['description']+='; Глыба: +2 урона Землёй'
        stun['damage_contribution']={'key':'boulder_stun','value':2,'type':'Земля','name':'Глыба · Оглушение','once_per_turn':False}
    return {'limit':2 if 'Двойной заряд' in learned else 1,'options':options,
            'uses':character.runtime.get('mystic_arrows',0),
            'next_penalty':1 if character.runtime.get('mystic_arrows',0) else 0}


def resolve(character, ability, calc, payload):
    available=profile(character,ability,calc)
    selected=payload.get('mystic_arrows',[])
    if not available:
        if selected:raise ValueError('Мистические стрелы требуют изученного пассива и стандартной атаки луком')
        return []
    if not isinstance(selected,list) or any(type(k) is not str for k in selected):
        raise ValueError('Выберите эффекты Мистической стрелы')
    if not 1<=len(selected)<=available['limit'] or len(set(selected))!=len(selected):
        raise ValueError('Выберите от 1 до '+str(available['limit'])+' разных эффектов Мистической стрелы')
    if any(k not in {o['id'] for o in OPTIONS} for k in selected):
        raise ValueError('Неизвестный эффект Мистической стрелы')
    if len(set(payload.get('targets',[])))>1:
        raise ValueError('Стандартная атака Мистической стрелой направлена на одну цель')
    return [next(o for o in available['options'] if o['id']==k) for k in selected]


def apply(change, character, targets, choices, payload, *, count_use=True, log_key='mystic_arrows'):
    if not choices:return
    change.watch(character)
    uses=character.runtime.get('mystic_arrows',0)
    if count_use:character.runtime['mystic_arrows']=uses+1
    if uses and count_use:
        effects=character.runtime.setdefault('effects',[])
        old=next((e for e in effects if e.get('key')=='status:Истощение маны'),None)
        value=(old['value'] if old else 0)-1
        if old:effects.remove(old)
        put_effect(character,{'key':'status:Истощение маны','name':'Истощение маны','status':'Истощение маны',
                              'stat':'hit','value':value,'duration':'battle','source':character.name,'source_id':character.id})
    from .outcomes import for_target
    missed=[t.pk for t in targets if for_target(payload,t.pk)=='miss']
    external=not targets
    targets=[t for t in targets if t.pk not in missed]
    hit=bool(targets) or external and for_target(payload,0)!='miss'
    change.inputs[log_key]={'choices':choices,'hit':hit,'penalty_added':1 if uses and count_use else 0,
                                    'use':uses+(1 if count_use else 0),'external_target':external,'target_ids':[t.pk for t in targets]}
    change.label+=' · '+', '.join(o['name'] for o in choices)
    if not hit:return
    change.inputs.setdefault('damage_contributions',[]).extend(o['damage_contribution'] for o in choices if o.get('damage_contribution'))
    for target in targets:
        for option in choices:
            if option.get('movement'):
                from .movement import forced
                change.depend(target)
                change.inputs[log_key].setdefault('movements',[]).append({'target':target.name,**forced(target,option['movement'])})
            if 'effect' not in option:continue
            effect=option['effect']
            apply_status(change.watch(target),{**effect,'key':'status:'+effect['status'],'name':effect['status'],
                'duration':effect.get('duration','turns'),'remaining':effect.get('turns',0),'source':character.name+' · '+option['name'],
                'source_id':character.id},payload.get('reactions',{}).get(f"{target.id}:arrow:{option['id']}"),change=change,roll=payload.get('reaction_rolls',{}).get(f"{target.id}:arrow:{option['id']}"))
