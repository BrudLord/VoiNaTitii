"""Book damage timing; HP remains an explicit master operation."""
from .statuses import status_name

PROFILES={
    'Поджог':('start',1,'Огонь',0),
    'Яд':('end',1,'Природа',0),
    'Кровотечение':('end',1,'Физический',0),
    'Продолжительный урон':('start',1,'',0),
    'Некропламя':('start',2,'',0),
    'Священное пламя':('start',1,'',1),
    'Вирус':('start',1,'',1),
}


def damage_events(character,phase=None):
    result=[]
    for effect in character.runtime.get('effects',[]):
        name=status_name(effect)
        if not name and effect.get('stat','status')=='status':name=effect.get('name','')
        profile=PROFILES.get(name)
        if not profile:continue
        timing,multiplier,kind,area=profile
        if phase and phase!=timing:continue
        amount=abs(effect.get('value',0))*multiplier
        if not amount:continue
        result.append({'character':character.pk,'target':character.name,'effect':name,'phase':timing,
                       'damage':amount,'damage_type':kind,'area':area,'source':effect.get('source','')})
    return result
