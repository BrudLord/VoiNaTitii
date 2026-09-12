"""Physical movement declarations; no map or automatic opportunity attacks."""
from .models import Entry, Character
from .rules import Change,availability,computed,current_scene
from .statuses import status_name


def apply(user,p):
    from .views import owned
    c=owned(user,p['character']);scene=current_scene(c);calc=computed(c)
    reason=availability(c,Entry(data={'action':'move'}),scene,calc)
    if reason:raise ValueError(reason)
    movement,sources=resolve(c,p,scene,calc)
    change=Change(user,('Шаг' if p['mode']=='step' else 'Движение')+' · '+c.name,scene,inputs={'movement':movement})
    for source in sources:change.depend(source)
    change.watch(c);change.action(c,'move');c.runtime['actions']['move']-=1
    change.finish()


def resolve(c,p,scene,calc=None,*,step_limit=None):
    calc=calc or computed(c)
    if any(status_name(e)=='Обездвижен' for e in c.runtime.get('effects',[])):
        raise ValueError('Обездвиженный персонаж не может двигаться или делать шаг')
    mode=p.get('mode');cells=p.get('cells');cost=p.get('cell_cost')
    if mode not in ['walk','step']:raise ValueError('Выберите движение или шаг')
    if type(cost) is not int or not 1<=cost<=1000:raise ValueError('Стоимость клетки должна быть целым числом от 1 до 1000')
    if type(cells) is not int or cells<1:raise ValueError('Укажите положительное целое число клеток')
    terrain=p.get('terrain',[])
    if not isinstance(terrain,list) or len(terrain)>100:raise ValueError('Укажите участки движения по Чистым льдам')
    sources={};segments=[]
    for row in terrain:
        if not isinstance(row,dict) or type(row.get('source')) is not int or type(row.get('cells')) is not int or row['cells']<1:
            raise ValueError('Укажите целое число клеток в области Чистых льдов')
        pk=row['source']
        if pk in sources or pk not in scene.state['order']:raise ValueError('Выберите разные области этого боя')
        source=c if pk==c.pk else Character.objects.get(pk=pk)
        strength=max((abs(e.get('value',0)) for e in source.runtime.get('effects',[]) if status_name(e)=='Чистые льды'),default=0)
        if not strength:raise ValueError('Область Чистых льдов уже не действует; обновите путь')
        sources[pk]=source
        segments.append({'source':pk,'name':source.name,'cells':row['cells'],'cell_cost':max(cost,strength)})
    zone_cells=sum(s['cells'] for s in segments)
    if zone_cells>cells:raise ValueError('Клеток в областях больше, чем всего клеток пути; пересечения считайте один раз')
    extra=sum(s['cells']*(s['cell_cost']-cost) for s in segments)
    limit=(calc['step'] if step_limit is None else step_limit) if mode=='step' else max(0,(calc['speed']-extra)//cost)
    if mode=='step' and any(s['cell_cost']>1 for s in segments):raise ValueError('Шаг невозможен через Чистые льды с повышенной стоимостью')
    if mode=='step' and cost!=1:raise ValueError('Шаг невозможен, если клетка стоит больше одной клетки движения')
    if cells>limit:raise ValueError(f'Доступно не более {limit} клеток')
    movement={'mode':mode,'cells':cells,'cell_cost':cost,'limit':limit,'provokes':mode!='step'}
    if segments:movement.update(terrain=segments,total_cost=cells*cost+extra)
    return movement,list(sources.values())


def forced(c,cells):
    calc=computed(c)
    if any(status_name(e)=='Обездвижен' for e in calc['effects']):
        return {'cells':0,'blocked':'Обездвижен'}
    return {'cells':max(0,cells-calc['forced_movement_reduction'])}
