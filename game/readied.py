"""Held actions expire with the round; failed Dexterity shifts the next round."""
from types import SimpleNamespace
import uuid
from .rules import availability, computed, current_scene, Change


def held_actions(c):
    return ([c.runtime['readied']] if c.runtime.get('readied') else [])+c.runtime.get('readied_queue',[])


def selected(c,action=None,key=None):
    return next((h for h in held_actions(c) if (key is None or h.get('key')==key) and (action is None or h['action']==action)),None)


def reason(c,scene,action,key=None):
    held=selected(c,action,key)
    if not scene or not held or held['round']!=scene.state['round']:
        return 'Нет подходящего отложенного действия'
    return ''


def reserve(user,p):
    from .views import owned
    c=owned(user,p['character']);scene=current_scene(c);key=p.get('action')
    if key not in ['main','move','minor']:raise ValueError('Выберите основное, движение или малое действие')
    blocked=availability(c,SimpleNamespace(data={'action':key}),scene)
    if blocked:raise ValueError(blocked)
    if c.runtime.get('actions',{}).get('minor',0)<(2 if key=='minor' else 1):
        raise ValueError('Чтобы отложить действие, нужно потратить ещё одно малое')
    condition=str(p.get('condition','')).strip()
    if not condition or len(condition)>500:raise ValueError('Опишите условие срабатывания — до 500 символов')
    change=Change(user,'Отложенное действие · '+c.name,scene,inputs={'condition':condition,'action':key})
    change.watch(c)
    c.runtime['actions']['minor']-=1;c.runtime['actions'][key]-=1
    held={'key':str(uuid.uuid4()),'action':key,'condition':condition,'round':scene.state['round']}
    if c.runtime.get('readied'):c.runtime.setdefault('readied_queue',[]).append(held)
    else:c.runtime['readied']=held
    change.finish()


def resolve(change,c,scene,p,action=None):
    held=selected(c,action,p.get('ready_id'))
    if not held or held['round']!=scene.state['round']:raise ValueError('Отложенное действие истекло')
    if p.get('triggered') is not True:raise ValueError('Подтвердите наступление условия')
    fail=p.get('voluntary_fail') is True
    roll=p.get('dex_roll')
    if not fail and (type(roll) is not int or not -1000<=roll<=1000):raise ValueError('Введите физический результат проверки Ловкости или выберите добровольный провал')
    bonus=computed(c)['mods']['dex'];total=None if fail else roll+bonus
    trigger=scene.state['order'][scene.state['turn']]
    change.watch(c)
    if fail or total<10:
        c.runtime['initiative_shift']={'after':trigger,'value':scene.state.get('initiative',{}).get(str(trigger),0)-1}
    check='Ловкость: добровольный провал' if fail else f'Ловкость: {roll} {bonus:+d} = {total} / 10'
    change.inputs['roll_result']=(change.inputs.get('roll_result','')+' · '+check).strip(' ·')
    change.inputs['readied']={**held,'dex_roll':None if fail else roll,'bonus':bonus,'total':total,'voluntary_fail':fail,'trigger':trigger}
    remaining=[h for h in held_actions(c) if h is not held]
    c.runtime.pop('readied',None);c.runtime.pop('readied_queue',None)
    if remaining:c.runtime['readied']=remaining[0];c.runtime['readied_queue']=remaining[1:]


def perform(user,p):
    from .views import owned
    c=owned(user,p['character']);scene=current_scene(c)
    if not scene:raise ValueError('Персонаж вне боя')
    held=selected(c,key=p.get('ready_id'))
    blocked=availability(c,SimpleNamespace(data={'action':held['action'] if held else None}),scene,readied=p.get('ready_id') or True)
    if blocked:raise ValueError(blocked)
    change=Change(user,'Выполнено отложенное действие · '+c.name,scene)
    resolve(change,c,scene,p)
    change.finish()


def next_round(scene,chars):
    order=scene.state['order'];shifts=[]
    for c in chars.values():
        c.runtime.pop('readied',None);c.runtime.pop('readied_queue',None)
        shift=c.runtime.pop('initiative_shift',None)
        if shift:
            scene.state.setdefault('initiative',{})[str(c.id)]=shift['value']
            shifts.append((c.id,shift['after']))
    for pk,after in shifts:
        if pk!=after and pk in order and after in order:
            order.remove(pk);order.insert(order.index(after)+1,pk)
