"""Declared damage reductions; HP remains under the master's control."""


def profile(ability):
    return ability.data.get('damage_reduction',{'divisor':2,'unarmed':True} if getattr(ability,'name','')=='Парирующие потоки' else None)


def validate(data):
    p=data.get('damage_reduction')
    if p is not None and (not isinstance(p,dict) or set(p)!={'divisor','unarmed'} or type(p['divisor']) is not int or not 1<=p['divisor']<=100 or type(p['unarmed']) is not bool):
        raise ValueError('Укажите делитель урона от 1 до 100 и условие отсутствия оружия')


def resolve(character,ability,payload,calc):
    p=profile(ability)
    if p is None:return None
    if p['unarmed'] and calc['has_equipped_weapons']:raise ValueError('Уберите оружие из рук для этой реакции')
    if payload.get('attack_hit') is not True:raise ValueError('Подтвердите, что атака попала по персонажу')
    damage=payload.get('incoming_damage')
    if type(damage) is not int or not 0<=damage<=100000:raise ValueError('Введите целый урон попавшей атаки от 0 до 100000')
    if payload.get('outcome','hit')!='hit':raise ValueError('Для уменьшения урона не нужен исход атаки персонажа')
    if any(pk!=character.pk for pk in payload.get('targets',[])):raise ValueError('Эта реакция защищает своего персонажа')
    return {'name':ability.display_name,'character':character.pk,'target':character.name,'incoming':damage,'divisor':p['divisor'],'remaining':damage/p['divisor']}
