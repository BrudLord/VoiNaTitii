"""Weapon upgrade profiles and attack ranges from the selected weapon."""
import re
from .models import Entry

UPGRADES={
 'Сбалансированный':{'families':['Мечи','Кинжалы','Древковое'],'hit':1},
 'Утяжеленный':{'families':['Булавы','Топоры','Цепы'],'crit':1},
 'Тугой':{'families':['Арбалеты','Луки'],'range':5},
 'Пробивающий':{'families':['Копья','Молоты'],'armored_hit':1},
}


def profile(entry):return entry.data.get('weapon_upgrade',UPGRADES.get(entry.name))


def upgrades(item):
    return [{'id':e.id,'name':e.name,**profile(e)} for e in Entry.objects.filter(pk__in=item.data.get('upgrades',[]),archived=False) if profile(e) and compatible(item,profile(e))]


def compatible(item, spec):
    names=set(item.data.get('families',[])+item.data.get('keywords',[]))
    aliases={'Лук':'Луки','Арбалет':'Арбалеты','Молот':'Молоты'}
    names={aliases.get(n,n) for n in names}
    return item.data.get('item_type')=='weapon' and bool(names.intersection(spec['families']))


def keywords(ability,calc):
    words=list(ability.data.get('keywords',[]))
    if not ability.data.get('weapon'):return melee_range(words,calc)
    words+= [w for w in calc.get('weapon_keywords',[]) if w in ['Одноручное','Двуручное'] and w not in words]
    if ability.data.get('system'):
        words=[w for w in words if not w.startswith(('Ближний','Дальнобойный','Метательное','Линия'))]
        ranged=next((w for w in calc.get('weapon_keywords',[]) if w.startswith('Дальнобойный')),None)
        thrown=next((w for w in calc.get('weapon_keywords',[]) if w.startswith('Метательное')),None)
        words.append(ranged or thrown.replace('Метательное','Дальнобойный') if calc.get('attack_mode')=='ranged' and thrown else ranged or 'Ближний')
        if thrown and calc.get('attack_mode')=='ranged':words.append('Метательное')
    bonus=calc.get('weapon_range_bonus',0)
    if bonus and ability.data.get('system'):words=[re.sub(r'Дальнобойный (\d+)',lambda m:'Дальнобойный '+str(int(m[1])+bonus),w) for w in words]
    return melee_range(words,calc)


def melee_range(words,calc):
    distance=1+calc.get('weapon_reach',0)
    return [('Линия '+str(distance) if calc.get('massive_strikes') else 'Ближний '+str(distance) if distance>1 else word) if re.fullmatch(r'Ближний(?: \d+)?',word) else word for word in words]


def effective(character,ability,calc=None):
    from .rules import computed
    import copy
    calc=calc or computed(character)
    if not calc['massive_strikes']:return ability
    words=keywords(ability,calc)
    if not calc['massive_strikes'] or not any(w.startswith('Линия ') for w in words):return ability
    if not any(re.fullmatch(r'Ближний(?: \d+)?',w) for w in ability.data.get('keywords',[])) and not ability.data.get('system'):return ability
    result=copy.copy(ability);result.data=copy.deepcopy(ability.data)
    result.data.update(keywords=words,target='multiple',range=next(w for w in words if w.startswith('Линия ')))
    return result


def validate(data):
    from types import SimpleNamespace
    ids=data.get('upgrades',[])
    if not isinstance(ids,list) or any(type(i) is not int for i in ids) or len(ids)>30 or len(set(ids))!=len(ids):raise ValueError('Выберите разные улучшения оружия')
    entries=list(Entry.objects.filter(pk__in=ids,archived=False))
    if len(entries)!=len(ids) or any(not profile(e) or not compatible(SimpleNamespace(data=data),profile(e)) for e in entries):
        raise ValueError('Улучшение не подходит к этому оружию')


def validate_profile(data):
    p=data.get('weapon_upgrade')
    if p is None:return
    if not isinstance(p,dict) or not isinstance(p.get('families'),list) or not p['families'] or any(not isinstance(k,str) for k in p['families']):raise ValueError('Укажите типы оружия для улучшения')
    for key,value in p.items():
        if key=='families':continue
        if key not in ['hit','crit','range','armored_hit'] or type(value) is not int or not 0<=value<=1000:raise ValueError('Некорректный параметр улучшения оружия')


def matches_keyword(keyword, words):
    def base(word):return re.sub(r'\s+\d+(?:\s+в\s+\d+)?$', '', str(word)).strip()
    return any(base(keyword)==base(word) for word in words)


def versatile(data):
    """The alternate dice are explicit in the book's Universal keyword."""
    for word in data.get('keywords',[]):
        match=re.fullmatch(r'Универсальное\s*\(?\s*(\d+к\d+)\s*\)?',word)
        if match:return match[1]
    return ''


def held_keywords(data):
    words=list(data.get('keywords',[]))+list(data.get('families',[]))
    if versatile(data):
        words=[w for w in words if w not in ['Одноручное','Двуручное']]
        words.append('Двуручное' if data.get('grip')=='two' else 'Одноручное')
    return list(dict.fromkeys(words))


def reload_action(data):
    for word in data.get('keywords',[]):
        if word=='Перезарядка малым':return 'minor'
        if word=='Перезарядка действием':return 'main'
    return ''


def reload_weapon(user,p):
    from .views import owned
    from .rules import computed, current_scene, Change
    from .statuses import status_name
    from .models import Item
    c=owned(user,p['character']);calc=computed(c)
    if p.get('item')!=calc['weapon_id'] or not calc['reload_action']:
        raise ValueError('Выберите оружие с перезарядкой')
    item=Item.objects.get(pk=calc['weapon_id'],character=c,equipped=True,archived=False,quantity__gt=0)
    if not item.data.get('needs_reload'):raise ValueError('Оружие уже заряжено')
    scene=current_scene(c);change=Change(user,'Перезарядка · '+item.name,scene)
    if scene:
        if scene.state['order'][scene.state['turn']]!=c.id:raise ValueError('Перезарядка доступна в свой ход')
        if c.runtime.get('stun_pending',0) or any(status_name(e) in ['Сон','Страх'] for e in c.runtime.get('effects',[])):
            raise ValueError('Сейчас персонаж должен пропускать действия')
        action=calc['reload_action']
        if c.runtime.get('actions',{}).get(action,0)<1:raise ValueError('Нет действия для перезарядки')
        change.watch(c).runtime['actions'][action]-=1
        change.action(c,action)
    change.watch(item).data['needs_reload']=False
    change.finish()


def discharge(change,c,ability):
    from .rules import computed
    if not ability.data.get('weapon'):return
    calc=computed(c)
    if not calc['reload_action']:return
    item=c.items.get(pk=calc['weapon_id'])
    change.watch(item).data['needs_reload']=True


def equip_action(item):
    if not item.equipped and not item.data.get('on_ground') and item.data.get('item_type')=='weapon' and set(item.data.get('keywords',[])).intersection({'Лёгкое','Легкое','Резервное'}):
        return 'minor'
    return 'main'


def wide_swing_profile(ability):
    default={'hit':1,'reach':1} if ability.name=='Широкий замах' else None
    return ability.data.get('wide_swing',default)


def validate_wide_swing(data):
    if 'wide_swing' not in data:return
    profile=data['wide_swing']
    if not isinstance(profile,dict) or set(profile)!={'hit','reach'}:
        raise ValueError('Укажите бонус попадания и досягаемость Широкого замаха')
    if type(profile['hit']) is not int or not -1000<=profile['hit']<=1000 or type(profile['reach']) is not int or not 0<=profile['reach']<=100:
        raise ValueError('Некорректные параметры Широкого замаха')
