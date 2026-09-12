"""Item enchantments from player-book chapter 9; no monster state or random rolls."""
from .models import Entry

BOOK = {
    'Малое изначальное зачарование': {'types':['armor'], 'initiative':3},
    'Малое зачарование огня': {'types':['weapon'], 'damage':1},
    'Малое зачарование воды': {'types':['armor'], 'start_temp':5},
    'Малое зачарование земли': {'types':['armor'], 'forced_movement_reduction':1},
    'Малое зачарование воздуха': {'types':['armor'], 'speed':1},
    'Малое зачарование тьмы': {'types':['weapon','focus'], 'first_kill_heal':5},
    'Малое зачарование света': {'types':['weapon','focus'], 'hit':1},
    'Малое зачарование молнии': {'types':['focus'], 'damage':1},
    'Малое зачарование холода': {'types':['weapon'], 'slow':1},
    'Малое зачарование природы': {'types':['focus'], 'first_loss_heal':3},
}


def profile(entry):
    return entry.data.get('enchantment', BOOK.get(entry.name.strip()))


def catalogue():
    return [{'id':e.id, 'name':e.name, 'description':e.description, **profile(e)}
            for e in Entry.objects.filter(archived=False) if profile(e)]


def validate(data):
    ids=data.get('enchantments',[])
    if not isinstance(ids,list) or len(ids)>30 or any(type(i) is not int for i in ids) or len(set(ids))!=len(ids):
        raise ValueError('Выберите разные зачарования из справочника')
    entries=list(Entry.objects.filter(pk__in=ids,archived=False))
    if len(entries)!=len(ids): raise ValueError('Зачарование не найдено')
    for entry in entries:
        p=profile(entry)
        if not p or data.get('item_type') not in p['types']:
            raise ValueError('Зачарование не подходит к предмету: '+entry.name)


def attached(item):
    for entry in Entry.objects.filter(pk__in=item.data.get('enchantments',[]),archived=False):
        p=profile(entry)
        if p and item.data.get('item_type') in p['types']:
            yield {'id':entry.id,'name':entry.name,'item_id':item.id,**p}


def equipment(character, equipped, selected):
    focuses=[i for i in equipped if i.data.get('item_type')=='focus']
    focus_id=character.runtime.get('focus_id')
    focus=None if focus_id==0 else next((i for i in focuses if str(i.id)==str(focus_id)),focuses[0] if focuses else None)
    active=[]
    for item in equipped:
        if item.data.get('item_type')=='weapon' and item!=selected: continue
        if item.data.get('item_type')=='focus' and item!=focus: continue
        active.extend({**p,'scope':item.data.get('item_type')} for p in attached(item))
    return active, focus.id if focus else None


def for_ability(calc, ability):
    scope='weapon' if ability.data.get('weapon') else 'focus'
    # A focus applies to magical abilities, not to every non-weapon action.
    magical=any(k in ['Магическое','Магический','Магия'] for k in ability.data.get('keywords',[]))
    magical=magical or any(k in ['Огонь','Вода','Земля','Воздух','Тьма','Свет','Молния','Холод','Природа'] for k in ability.data.get('keywords',[]))
    magical=magical or ability.data.get('school_name') in ['Огонь','Вода','Земля','Воздух','Тьма','Свет','Молния','Холод','Природа']
    return [p for p in calc.get('enchantments',[]) if p['scope']==scope and (scope=='weapon' or magical)]


def start_battle(character, calc):
    character.runtime['enchantment_uses']={}
    character.runtime['temp']=max(character.runtime.get('temp',0),max((p.get('start_temp',0) for p in calc['enchantments']),default=0))


def restore_first_loss(character, calc, lost):
    limit=max((p.get('first_loss_heal',0) for p in calc['enchantments']),default=0)
    uses=character.runtime.setdefault('enchantment_uses',{})
    # Track all actual HP lost, even while the focus is not equipped.
    previous=uses.get('hp_lost',0)
    uses['hp_lost']=previous+lost
    healed=min(lost,max(0,limit-previous))
    character.runtime['hp']=min(calc['max_hp'],character.runtime['hp']+healed)
    return healed


def validate_profile(data):
    p=data.get('enchantment')
    if p is None: return
    if not isinstance(p,dict) or not isinstance(p.get('types'),list) or not p['types'] or any(t not in ['weapon','armor','focus','shield'] for t in p['types']):
        raise ValueError('Укажите допустимые типы предметов для зачарования')
    for key,value in p.items():
        if key=='types':continue
        if key not in ['hit','damage','speed','initiative','forced_movement_reduction','start_temp','first_kill_heal','first_loss_heal','slow'] or type(value) is not int or not 0<=value<=1000:
            raise ValueError('Некорректный параметр зачарования: '+key)


def ability_bonus(calc, ability, stat):
    from .weaponry import keywords, matches_keyword
    words=keywords(ability,calc)
    magical=not ability.data.get('weapon') and bool(for_ability({**calc,'enchantments':[{'scope':'focus'}]},ability))
    scopes={'weapon'} if ability.data.get('weapon') else {'focus'} if magical else set()
    return sum(e.get('value',0) for e in calc['effects'] if e.get('stat')==stat
               and (not e.get('ability_scope') or e['ability_scope'] in scopes)
               and (not e.get('keyword') or matches_keyword(e['keyword'],words)))
