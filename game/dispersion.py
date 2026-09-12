"""Spread a selected primary effect to physically selected opponents."""
import copy
from .models import Character


def apply(change,center,incoming,old,spread):
    from .statuses import apply_status,status_name
    if change is None or not change.scene:raise ValueError('Рассеивание применяется в активном бою')
    if not isinstance(spread,dict) or spread.get('in_range') is not True:
        raise ValueError('Выберите получателей Рассеивания и подтвердите область')
    ids=spread.get('targets',[])
    if not isinstance(ids,list) or any(type(i) is not int for i in ids) or len(set(ids))!=len(ids) or center.pk in ids or any(i not in change.scene.state['order'] for i in ids):
        raise ValueError('Выберите других участников этого боя для Рассеивания')
    for key in ['remove_source','external']:
        if type(spread.get(key,False)) is not bool:raise ValueError('Подтвердите условия Рассеивания')
    reactions=spread.get('reactions',{});rolls=spread.get('rolls',{})
    if not isinstance(reactions,dict) or not isinstance(rolls,dict):raise ValueError('Выберите реакции получателей')
    recipients=[]
    for pk in ids:
        target=change.objects.get('character:'+str(pk)) or getattr(change,'effect_targets',{}).get(pk) or Character.objects.get(pk=pk)
        change.watch(target)
        effect=copy.deepcopy(old)
        effect.update(key='status:'+status_name(old),status=status_name(old),duration='turns',remaining=old.get('max_turns',3),max_turns=old.get('max_turns',3),source=incoming.get('source',''),source_id=incoming.get('source_id'))
        effect.pop('aura_source',None)
        apply_status(target,effect,reactions.get(str(pk)),change=change,roll=rolls.get(str(pk)))
        recipients.append({'id':pk,'name':target.name})
    if spread.get('remove_source'):center.runtime['effects'].remove(old)
    change.inputs.setdefault('dispersions',[]).append({'center':center.name,'center_id':center.pk,'effect':status_name(old),'strength':abs(old['value']),
        'radius':abs(incoming['value']),'targets':recipients,'removed':spread.get('remove_source',False),'external':spread.get('external',False)})
