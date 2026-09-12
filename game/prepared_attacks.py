"""Conditional effects armed now and consumed by a later successful attack."""
from .statuses import status_name


def exhaustion(character):
    return sum(abs(e.get('value',0)) for e in character.runtime.get('effects',[])
               if status_name(e)=='Истощение маны' and e.get('stat')=='hit')


def profile(character,ability):
    if ability.name=='Передача истощения':
        return {'prepare':True,'strength':exhaustion(character)}
    pending=character.runtime.get('exhaustion_transfer')
    if pending and ability.data.get('category','active')=='active' and (ability.data.get('damage') or ability.data.get('weapon')):
        return {'prepare':False,'strength':pending['strength']}


def validate(character,ability,payload,ids):
    p=profile(character,ability)
    if not p:return None
    if p['prepare']:
        if not p['strength']:raise ValueError('Нет истощения маны для передачи')
        if ids:raise ValueError('Цель передачи выбирается при следующем попадании')
        return p
    if payload.get('outcome','hit')=='miss':return None
    chosen=payload.get('exhaustion_target')
    if type(chosen) is int and chosen==0:
        if ids and (ability.data.get('system') or ability.data.get('target')=='single'):
            raise ValueError('Передача должна попасть в ту же цель, что и одиночная атака')
        return {**p,'target':None}
    from .outcomes import for_target
    hit_ids=[pk for pk in ids if for_target(payload,pk)!='miss']
    if chosen is None and len(hit_ids)==1:chosen=hit_ids[0]
    if chosen is not None and (type(chosen) is not int or chosen not in ids):
        raise ValueError('Выберите получателя истощения среди целей атаки')
    if chosen in ids and chosen not in hit_ids:raise ValueError('Выберите получателя истощения, в которого попали')
    if len(ids)>1 and chosen is None:raise ValueError('Выберите одну цель для передачи истощения')
    return {**p,'target':chosen}


def apply(change,character,ability,targets,resolved):
    if not resolved:return
    change.watch(character)
    if resolved['prepare']:
        character.runtime['exhaustion_transfer']={'strength':resolved['strength'],'ability':ability.id}
        change.inputs['exhaustion_transfer']={'prepared':True,'strength':resolved['strength']}
        return
    pk=resolved['target']
    if pk is not None:
        target=change.watch(targets[pk])
        previous=exhaustion(target)
        target.runtime['effects']=[e for e in target.runtime.get('effects',[]) if status_name(e)!='Истощение маны']
        target.runtime['effects'].append({'key':'status:Истощение маны','status':'Истощение маны','name':'Истощение маны',
            'stat':'hit','value':-previous-resolved['strength'],'duration':'battle','source':character.name,'source_id':character.id})
    change.inputs['exhaustion_transfer']={'prepared':False,'strength':resolved['strength'],'target':targets[pk].name if pk is not None else 'Цель на игровом поле'}
    character.runtime.pop('exhaustion_transfer',None)
