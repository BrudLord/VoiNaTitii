"""The book's Capture weapon action, with a reversible dropped item."""
import copy
from .models import Character,Item,Entry
from .rules import Change,computed,current_scene,availability
from . import targeting,weaponry


def attack(calc):
    return Entry(name='Обезоруживание',data={'category':'active','action':'main','circle':0,'weapon':True,'damage':False,'formula':'','keywords':weaponry.melee_range(['Ближний'],{**calc,'massive_strikes':False})})


def profile(c,calc,scene):
    if 'Захват' not in calc['weapon_keywords']:return None
    calc={**calc,'massive_strikes':False}
    a=attack(calc)
    return {'roll_conditions':targeting.roll_conditions(a,calc),'reason':availability(c,a,scene,calc),'hit':targeting.hit_bonus(c,a,calc),'keywords':a.data['keywords']}


def apply(user,p):
    from .views import owned
    c=owned(user,p['character']);calc={**computed(c),'massive_strikes':False};scene=current_scene(c)
    spec=profile(c,calc,scene)
    if not spec:raise ValueError('Обезоруживание требует оружия со свойством Захват')
    if spec['reason']:raise ValueError(spec['reason'])
    if p.get('outcome') not in ['hit','miss']:raise ValueError('Укажите попадание или промах')
    roll=str(p.get('roll_result','')).strip()
    if not roll:raise ValueError('Введите результат физического броска на попадание')
    if p.get('in_range') is not True:raise ValueError('Подтвердите, что цель в пределах досягаемости')
    pk=p.get('target');target=None;item=None
    if pk:
        if type(pk) is not int or pk==c.pk or pk not in scene.state['order']:raise ValueError('Выберите другую цель в бою')
        target=Character.objects.get(pk=pk)
        item=Item.objects.filter(pk=p.get('item'),character=target,equipped=True,archived=False,quantity__gt=0,data__item_type__in=['weapon','shield','focus']).first()
        if not item:raise ValueError('Выберите предмет в руках цели')
    elif not str(p.get('external_item','')).strip():raise ValueError('Укажите предмет противника на поле')
    change=Change(user,'Обезоруживание · '+c.name,scene,inputs={'roll_result':roll[:2000],'outcome':p['outcome']})
    change.watch(c);change.action(c,'main');c.runtime['actions']['main']-=1
    rows=targeting.resolve(c,attack(calc),calc,[target] if target else [],p)
    change.inputs['attack_targets']=rows
    for held in c.items.filter(equipped=True,archived=False):change.depend(held)
    change.inputs['disarm']={'target':target.name if target else 'Противник на поле','item':item.name if item else str(p['external_item'])[:160],'hit':p['outcome']=='hit'}
    if target:
        change.depend(target);change.depend(item)
        if p['outcome']=='hit':
            change.watch(target);change.watch(item)
            selected=computed(target)
            item.equipped=False
            if selected['weapon_id']==item.pk:target.runtime['weapon_id']=0
            if selected['focus_id']==item.pk:target.runtime['focus_id']=0
            dropped=item
            if item.quantity>1:
                from .inventory import new_item
                item.quantity-=1;dropped=new_item(change,target)
                dropped.name=item.name;dropped.entry_id=item.entry_id;dropped.quantity=1;dropped.data=copy.deepcopy(item.data)
            dropped.data={**dropped.data,'on_ground':True}
    change.finish()
