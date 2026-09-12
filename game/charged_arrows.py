"""Book: a prepared effect slot for each Ор of the next circle 1+ ability."""
import re
from .mystic_arrows import OPTIONS, apply as apply_arrows

NAME = 'Заряженные стрелы'


def profile(character, ability):
    if ability.name == NAME:
        return {'prepare': True}
    d = ability.data
    if not character.runtime.get('charged_arrows') or d.get('category','active') != 'active' or int(d.get('circle',0)) < 1:
        return None
    count = sum(int(n) for n in re.findall(r'(\d+)\s*Ор',d.get('formula',''))) if d.get('damage') else 0
    options = [dict(o) for o in OPTIONS]
    if any(a.name == 'Глыба' and not a.archived for a in character.abilities.all()):
        option = next(o for o in options if o['id']=='stun')
        option['damage_contribution'] = {'key':'boulder_stun','value':2,'type':'Земля','name':'Глыба · Оглушение','once_per_turn':False}
    return {'prepare':False,'limit':count,'options':options}


def resolve(character, ability, payload, ids):
    p = profile(character,ability)
    selected = payload.get('charged_arrows',[])
    if not p:
        if selected:raise ValueError('Сначала подготовьте Заряженные стрелы')
        return None
    if p['prepare']:
        if selected or ids:raise ValueError('Эффекты и цель выбираются при следующем умении')
        return p
    if not isinstance(selected,list) or len(selected)>p['limit'] or any(type(k) is not str for k in selected):
        raise ValueError('Число эффектов Заряженных стрел не должно превышать число Ор урона')
    options = {o['id']:o for o in p['options']}
    if any(k not in options for k in selected):raise ValueError('Неизвестный эффект Заряженной стрелы')
    target = payload.get('charged_target')
    if selected:
        if target is None and len(ids)==1:target=ids[0]
        if target is None and not ids:target=0
        if type(target) is not int or (target!=0 and target not in ids):
            raise ValueError('Выберите получателя Заряженных стрел среди целей умения')
        if target==0 and ids and (ability.data.get('system') or ability.data.get('target')=='single'):
            raise ValueError('Заряженные стрелы должны попасть в ту же цель, что и одиночная атака')
    return {**p,'target':target,'choices':[{**options[k],'id':f'charged:{i}:{k}'} for i,k in enumerate(selected)]}


def apply(change, character, ability, targets, resolved, payload):
    if not resolved:return
    change.watch(character)
    if resolved['prepare']:
        character.runtime['charged_arrows'] = {'ability':ability.id}
        change.inputs['charged_arrows'] = {'prepared':True}
        return
    character.runtime.pop('charged_arrows',None)
    choices = resolved['choices']
    if choices:
        recipient = resolved['target']
        apply_arrows(change,character,[targets[recipient]] if recipient else [],choices,payload,
                     count_use=False,log_key='charged_arrows')
    else:
        change.inputs['charged_arrows'] = {'skipped':True,'limit':resolved['limit']}
