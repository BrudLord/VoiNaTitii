"""Physical movement declarations; no map or automatic opportunity attacks."""
from .models import Entry
from .rules import Change,availability,computed,current_scene
from .statuses import status_name


def apply(user,p):
    from .views import owned
    c=owned(user,p['character']);scene=current_scene(c);calc=computed(c)
    reason=availability(c,Entry(data={'action':'move'}),scene,calc)
    if reason:raise ValueError(reason)
    if any(status_name(e)=='Обездвижен' for e in c.runtime.get('effects',[])):
        raise ValueError('Обездвиженный персонаж не может двигаться или делать шаг')
    mode=p.get('mode');cells=p.get('cells');cost=p.get('cell_cost')
    if mode not in ['walk','step']:raise ValueError('Выберите движение или шаг')
    if type(cost) is not int or not 1<=cost<=1000:raise ValueError('Стоимость клетки должна быть целым числом от 1 до 1000')
    if type(cells) is not int or cells<1:raise ValueError('Укажите положительное целое число клеток')
    limit=calc['step'] if mode=='step' else calc['speed']//cost
    if mode=='step' and cost!=1:raise ValueError('Шаг невозможен, если клетка стоит больше одной клетки движения')
    if cells>limit:raise ValueError(f'Доступно не более {limit} клеток')
    change=Change(user,('Шаг' if mode=='step' else 'Движение')+' · '+c.name,scene,
                  inputs={'movement':{'mode':mode,'cells':cells,'cell_cost':cost,'limit':limit,'provokes':mode!='step'}})
    change.watch(c);change.action(c,'move');c.runtime['actions']['move']-=1
    change.finish()


def forced(c,cells):
    calc=computed(c)
    if any(status_name(e)=='Обездвижен' for e in calc['effects']):
        return {'cells':0,'blocked':'Обездвижен'}
    return {'cells':max(0,cells-calc['forced_movement_reduction'])}
