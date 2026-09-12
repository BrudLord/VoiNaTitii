"""Physical dice and explicitly allocated resources; rolled HP stays master-controlled."""
PROFILES = {
    'Ритуал восстановления': {'dice':9, 'sides':6, 'cleanse_cost':5},
    'Исход небес': {'dice':6, 'sides':6, 'parity':True},
}


def profile(ability):
    return PROFILES.get(ability.name)


def resolve(ability, payload, targets):
    spec=profile(ability)
    if not spec:return None
    dice=payload.get('dice')
    if not isinstance(dice,list) or len(dice)!=spec['dice'] or any(type(v) is not int or not 1<=v<=spec['sides'] for v in dice):
        raise ValueError(f"Введите все {spec['dice']} физических результатов к{spec['sides']}")
    healing=sum(v for v in dice if not spec.get('parity') or v%2)
    damage=sum(v for v in dice if spec.get('parity') and not v%2)
    allocations=payload.get('allocations',[])
    if spec.get('parity'):
        assignments=payload.get('dice_targets')
        if not isinstance(assignments,list) or len(assignments)!=len(dice):raise ValueError('Укажите получателей нечётных кубиков')
        grouped={}
        for value,pk in zip(dice,assignments):
            if pk is None:continue
            if value%2==0 or type(pk) is not int or pk not in targets:raise ValueError('Нечётный кубик можно назначить участнику боя; чётные — урон противникам')
            grouped[pk]=grouped.get(pk,0)+value
        allocations=[{'character':pk,'hp':hp} for pk,hp in grouped.items()]
    if not isinstance(allocations,list) or len(allocations)>len(targets):raise ValueError('Проверьте распределение лечения')
    result=[];seen=set();spent=0
    for row in allocations:
        if not isinstance(row,dict):raise ValueError('Проверьте распределение лечения')
        pk=row.get('character');hp=row.get('hp',0);remove=row.get('remove',[])
        if type(pk) is not int or pk not in targets or pk in seen:raise ValueError('Выберите разных участников боя')
        seen.add(pk)
        if type(hp) is not int or not 0<=hp<=healing:raise ValueError('Некорректное количество лечения')
        if not isinstance(remove,list) or any(not isinstance(k,str) for k in remove) or len(set(remove))!=len(remove):raise ValueError('Выберите разные эффекты для снятия')
        if remove and not spec.get('cleanse_cost'):raise ValueError('Это умение не снимает эффекты')
        current={e['key']:e for e in targets[pk].runtime.get('effects',[])}
        if any(k not in current or current[k].get('duration')=='aura' for k in remove):raise ValueError('Эффект уже изменился или поддерживается аурой')
        spent+=hp+len(remove)*spec.get('cleanse_cost',0)
        result.append({'character':pk,'hp':hp,'remove':remove})
    if spent>healing:raise ValueError('Распределено больше, чем выпало на кубиках')
    return {'dice':dice,'healing_pool':healing,'damage_pool':damage,'spent':spent,'unused':healing-spent,'allocations':result,'dice_targets':payload.get('dice_targets')}
