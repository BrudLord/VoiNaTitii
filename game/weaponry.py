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
    if not ability.data.get('weapon'):return words
    words+= [w for w in calc.get('weapon_keywords',[]) if w in ['Одноручное','Двуручное'] and w not in words]
    if ability.data.get('system'):
        words=[w for w in words if not w.startswith(('Ближний','Дальнобойный','Метательное'))]
        ranged=next((w for w in calc.get('weapon_keywords',[]) if w.startswith('Дальнобойный')),None)
        thrown=next((w for w in calc.get('weapon_keywords',[]) if w.startswith('Метательное')),None)
        words.append(ranged or thrown.replace('Метательное','Дальнобойный') if calc.get('attack_mode')=='ranged' and thrown else ranged or 'Ближний')
    bonus=calc.get('weapon_range_bonus',0)
    if bonus and ability.data.get('system'):words=[re.sub(r'Дальнобойный (\d+)',lambda m:'Дальнобойный '+str(int(m[1])+bonus),w) for w in words]
    return words


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
