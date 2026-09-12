"""Elemental Support stance modes and their explicit resource costs."""
import copy
import uuid
from types import SimpleNamespace

NAME='Стихийная поддержка'
MODES=['Огонь','Вода','Земля','Воздух']


def learned(c,name):
    return any(a.name==name and not a.archived for a in c.abilities.all())


def mode(c):
    value=c.runtime.get('elemental_support',{}).get('mode')
    return value if value in MODES and learned(c,NAME) else None


def effective(c,a):
    if a.name!=NAME:return a
    a=copy.copy(a);a.data=copy.deepcopy(a.data)
    a.data.update(damage=False,weapon=False,formula='',effects=[],rolls=False,manual=False,
                  action='minor' if learned(c,'Стихийное превосходство') else 'main',category='active')
    return a


def activation(c,a,p):
    if a.name!=NAME:return None
    value=p.get('stance_mode')
    if value not in MODES:raise ValueError('Выберите стихию стойки')
    if p.get('targets'):raise ValueError('Стойка применяется к своему персонажу')
    return {'ability':a.pk,'mode':value}


def mutate(user,p):
    from .views import owned
    from .rules import current_scene, computed, availability, Change
    from .passives import turn_token
    from .models import Character
    c=owned(user,p['character']);scene=current_scene(c)
    if not scene or not mode(c):raise ValueError('Сначала активируйте Стихийную поддержку')
    switching=p['op']=='stance.switch'
    reason=availability(c,SimpleNamespace(data={'action':'minor' if switching else 'free'}),scene)
    if reason:raise ValueError(reason)
    change=Change(user,('Смена стихии' if switching else 'Стихийная поддержка · Вода')+' · '+c.name,scene)
    change.watch(c)
    if switching:
        value=p.get('stance_mode')
        if value not in MODES or value==mode(c):raise ValueError('Выберите другой режим стойки')
        c.runtime['actions']['minor']-=1
        c.runtime['elemental_support']['mode']=value
        change.inputs['stance_mode']=value
    else:
        if mode(c)!='Вода':raise ValueError('Лечение доступно в режиме Воды')
        token=turn_token(scene)
        if c.runtime.get('once_per_turn',{}).get('support_water')==token:
            raise ValueError('Вода уже использована на этом ходу')
        pk=p.get('target')
        if type(pk) is not int or pk not in scene.state['order']:raise ValueError('Выберите союзника в текущем бою')
        if p.get('in_range') is not True:raise ValueError('Подтвердите расстояние до 5 клеток')
        target=c if pk==c.pk else Character.objects.get(pk=pk)
        change.depend(target)
        calc=computed(c);amount=max(0,calc['mods'][calc['primary']])
        remove=p.get('remove')
        if remove:
            if not learned(c,'Стихийное превосходство'):raise ValueError('Для снятия эффекта нужно Стихийное превосходство')
            effect=next((e for e in target.runtime.get('effects',[]) if e['key']==remove and e.get('duration')!='aura'),None)
            if not effect:raise ValueError('Выберите действующий эффект, кроме поддерживаемой ауры')
            change.watch(target).runtime['effects'].remove(effect)
        if amount:
            c.runtime.setdefault('pending_heals',{})[str(uuid.uuid4())]={'scene':scene.pk,'name':'Стихийная поддержка · Вода',
                'allocations':[{'character':pk,'hp':amount}],'dice':[]}
        c.runtime.setdefault('once_per_turn',{})['support_water']=token
        change.inputs.update(target=pk,healing_pending=amount,removed=remove)
    change.finish()


def minor_attack(c,a):
    d=a.data
    if (mode(c)!='Огонь' or not learned(c,'Стихийное превосходство')
            or d.get('category','active')!='active' or int(d.get('circle',0))!=0
            or d.get('action','main')!='main' or not (d.get('damage') or d.get('weapon'))):
        return None
    result=copy.copy(a);result.data=copy.deepcopy(d);result.data['action']='minor'
    return result
