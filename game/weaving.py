"""A standard attack and its woven spell form one undoable operation."""
from . import enchantments
from .models import Entry

NAME='Мистическое плетение'


def magical(ability):
    return (not ability.data.get('weapon') and ability.data.get('category','active')=='active'
            and int(ability.data.get('circle',0))>=1
            and bool(enchantments.for_ability({'enchantments':[{'scope':'focus'}]},ability)))


def standard(ability):
    return ability.name=='Стандартная атака' and ability.data.get('system')


def area(ability):
    return any(k.startswith(('Сфера','Вокруг','Конус','Линия')) for k in ability.data.get('keywords',[]))


def resolve(character,ability,payload,ids):
    child=payload.get('weave')
    if ability.name==NAME:
        if ids or child:raise ValueError('Цель и магическое умение выбираются при стандартной атаке')
        return {'prepare':True}
    if not character.runtime.get('mystic_weaving') or not standard(ability):
        if child:raise ValueError('Сначала подготовьте Мистическое плетение и выполните стандартную атаку')
        return None
    if len(ids)>1:raise ValueError('У стандартной атаки должна быть одна цель')
    if not child:return {'prepare':False,'child':None}
    if not isinstance(child,dict):raise ValueError('Выберите магическое умение')
    spell=Entry.objects.filter(pk=child.get('ability'),kind='ability',archived=False).first()
    if not spell or not magical(spell) or not character.abilities.filter(pk=spell.pk).exists():
        raise ValueError('Выберите изученное магическое умение первого круга или выше')
    if any(child.get(k) for k in ['weave','as_reaction','use_ready']):raise ValueError('Плетение применяет одно магическое умение без дополнительного действия')
    selected=list(dict.fromkeys(int(i) for i in child.get('targets',[])))
    if area(spell):
        if child.get('area_center_confirmed') is not True:
            raise ValueError('Подтвердите область с центром на цели стандартной атаки')
    elif selected!=ids:
        raise ValueError('Магическое умение должно применяться к цели стандартной атаки')
    return {'prepare':False,'spell':spell.name,'center':ids,'child':{**child,'op':'ability.use','character':character.pk}}
