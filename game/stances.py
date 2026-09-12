"""Elemental Support stance modes and their explicit resource costs."""
import copy
import uuid
from types import SimpleNamespace

NAME='Стихийная поддержка'
MODES=['Огонь','Вода','Земля','Воздух']
SPHERE='Элементальная сфера'
SPHERE_EFFECTS={'Огонь':'Поджог','Вода':'Влага','Земля':'Кислота','Воздух':'Рассеивание'}

def sphere_profile(a):
    return a.data.get('elemental_sphere',{'strength':1} if getattr(a,'name','')==SPHERE else None)

def validate_sphere(data):
    p=data.get('elemental_sphere')
    if p is not None and (not isinstance(p,dict) or set(p)!={'strength'} or type(p['strength']) is not int or not 0<=p['strength']<=1000):
        raise ValueError('Укажите целую силу первородного эффекта от 0 до 1000')



def learned(c,name):
    return any(a.name==name and not a.archived for a in c.abilities.all())


def mode(c):
    value=c.runtime.get('elemental_support',{}).get('mode')
    return value if value in MODES and learned(c,NAME) else None


def effective(c,a):
    sphere=sphere_profile(a)
    if sphere is not None:
        from .statuses import STATUS
        a=copy.copy(a);a.data=copy.deepcopy(a.data)
        element=mode(c)
        effects=[e for e in a.data.get('effects',[]) if not e.get('elemental_sphere')]
        if element:
            name=SPHERE_EFFECTS[element];stat,sign=STATUS[name]
            effects.append({'name':name,'key':'sphere:element','stat':stat,'value':sign*sphere['strength'],'turns':3,'elemental_sphere':True})
        words=[w for w in a.data.get('keywords',[]) if w not in MODES]
        if element:words.append(element)
        a.data.update(elemental_sphere=sphere,effects=effects,keywords=words,damage_type=element or '',manual=False,
                      damage=True,weapon=False,target=a.data.get('target','single'),formula=a.data.get('formula','1к8'))
    if a.name!=NAME:
        if not learned(c,'Огонь и Вода'):return a
        from .statuses import status_name
        effects=copy.deepcopy(a.data.get('effects',[]))
        changed=False
        for effect in effects:
            if status_name(effect) in ['Поджог','Влага'] and not effect.get('manual') and effect.get('source_bonus')!='Огонь и Вода':
                effect['base_value']=effect.get('value',0)
                effect['value']=effect['base_value']+1
                effect['source_bonus']='Огонь и Вода'
                changed=True
        if not changed:return a
        a=copy.copy(a);a.data=copy.deepcopy(a.data);a.data['effects']=effects
        return a
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
    change.action(c,'minor' if switching else 'free')
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


def controls(c,scene,calc):
    from .rules import availability
    from .passives import turn_token
    if not calc.get('support'):return None
    switch=availability(c,SimpleNamespace(data={'action':'minor'}),scene,calc)
    water=availability(c,SimpleNamespace(data={'action':'free'}),scene,calc)
    if scene and c.runtime.get('once_per_turn',{}).get('support_water')==turn_token(scene):
        water='Уже использовано в этом ходу'
    return {'switch_reason':switch,'water_reason':water}
