import copy
import re
from .models import Character, Entry, Event, Scene, Item
from .book_audit import SKILLS

STATS = [('str', 'Сила'), ('dex', 'Ловкость'), ('con', 'Телосложение'),
         ('int', 'Интеллект'), ('wis', 'Мудрость'), ('cha', 'Харизма')]
ACTIONS = {'main': 1, 'minor': 1, 'move': 1}


def fresh():
    return {'hp': 0, 'temp': 0, 'used': {}, 'actions': dict(ACTIONS), 'effects': [], 'turns': 0}


def definition(pk):
    return Entry.objects.filter(pk=pk).first() if str(pk).isdigit() else None


def computed(c):
    stats = {k: int(c.stats.get(k, 10)) for k, _ in STATS}
    equipped = list(c.items.filter(equipped=True,quantity__gt=0,archived=False).order_by('id'))
    weapons = [i for i in equipped if i.data.get('dice')]
    weapon_id=c.runtime.get('weapon_id',c.info.get('weapon_id'))
    selected = None if weapon_id==0 else next((i for i in weapons if str(i.id)==str(weapon_id)),weapons[0] if weapons else None)
    from .enchantments import equipment
    enchantments, focus_id = equipment(c, equipped, selected)
    from .weaponry import upgrades, versatile, held_keywords, reload_action, offhand_penalty
    from .passives import lightning_reflexes
    from .stances import mode, learned as stance_learned
    support=mode(c);support_mastery=stance_learned(c,'Стихийное превосходство')
    weapon_upgrades=upgrades(selected) if selected else []
    effects = list(c.runtime.get('effects', []))
    if support=='Земля':effects.append({'name':'Стихийная поддержка · Земля','stat':'ac','value':2})
    if selected and selected.data.get('accuracy_oil'):
        effects.append({'stat':'hit','value':1,'ability_scope':'weapon','name':'Масло точности'})
    effects.extend({'stat':'hit','value':p['hit'],'ability_scope':'weapon'} for p in weapon_upgrades if p.get('hit'))
    effects.extend({'stat':'speed','value':p['speed']} for p in enchantments if p.get('speed'))
    effects.extend({**e,**({'ability_scope':'weapon' if i.data.get('dice') else 'focus'} if (i.data.get('dice') or i.data.get('item_type')=='focus') and e.get('stat') in ['hit','damage'] else {})} for i in equipped for e in i.data.get('effects',[])
                   if not ((i.data.get('dice') and i!=selected or i.data.get('item_type')=='focus' and i.id!=focus_id) and e.get('stat') in ['hit','damage']))
    learned = [a for a in c.abilities.all() if not a.archived]
    from .weaponry import wide_swing_profile, unarmed_profile
    swings=[(a,wide_swing_profile(a)) for a in learned if wide_swing_profile(a) is not None]
    weapon_words=held_keywords(selected.data) if selected else []
    for ability,profile in swings:
        effects.append({'name':ability.display_name,'stat':'hit','value':profile['hit']})
    if 'Двуручное' in weapon_words and swings:
        reach=max([p['reach'] for a,p in swings]+[int(m[1]) for w in weapon_words if (m:=re.fullmatch(r'Досягаемость (\d+)',w))])
        weapon_words=[w for w in weapon_words if not re.fullmatch(r'Досягаемость (\d+)',w)]
        if reach:weapon_words.append('Досягаемость '+str(reach))
    for ability in learned:
        if ability.data.get('category') == 'passive' and not ability.data.get('aura') and not ability.data.get('manual'):
            effects.extend(e for e in ability.data.get('effects', []) if not e.get('manual'))
    for e in effects:
        if e.get('stat') in stats:
            stats[e['stat']] += e.get('value', 0)
    mods = {k: (v - 10) // 2 for k, v in stats.items()}
    klass = definition(c.info.get('class_id'))
    race = definition(c.info.get('race_id'))
    school = definition(c.info.get('school_id'))
    kd = klass.data if klass else {}
    rd = race.data if race else {}
    primary = (school.data if school else {}).get('stat', 'wis')
    armor = 0
    other_armor = 0
    warnings = []
    bonuses = {'ac': 0, 'speed': 0, 'hit': 0, 'damage': 0}
    keywords = []
    weapon = ''
    weapon_item = None
    weapon_proficient = False
    weapon_hit = 0
    weapon_school = primary
    crit = sum(p.get('crit',0) for p in weapon_upgrades)
    school_ids = [c.info.get('school_id'),c.info.get('secondary_school_id')] + c.info.get('additional_school_ids',[])
    trained = {e.name for e in Entry.objects.filter(pk__in=[x for x in school_ids if str(x).isdigit()],kind='school')}
    if any(a.name == 'Интуитивное владение' for a in learned):
        trained.add('Луки')
    for item in equipped:
        if item.data.get('item_type') in ['armor','shield'] or not item.data.get('item_type'):
            armor += int(item.data.get('armor', 0))
        else:
            other_armor += int(item.data.get('armor', 0))
        if not item.data.get('dice') or item == selected:
            keywords += held_keywords(item.data)
        if selected and item.pk == selected.pk:
            weapon = versatile(item.data) if versatile(item.data) and item.data.get('grip')=='two' else item.data['dice']
            trained_family = next((name for name in item.data.get('families',[]) if name in trained),None)
            matched_school = Entry.objects.filter(kind='school',name=trained_family).first() if trained_family else None
            weapon_school = matched_school.data.get('stat',primary) if matched_school else item.data.get('stat', primary)
            crit += int(item.data.get('crit', 0))
            weapon_item = item.id
            weapon_proficient = bool(item.data.get('no_proficiency') or trained.intersection(item.data.get('families',item.data.get('keywords',[]))))
            weapon_hit = int(item.data.get('hit',0)) + offhand_penalty(item.data)
    unarmed_profiles=[p for a in learned if a.data.get('category','passive')=='passive' and (p:=unarmed_profile(a)) is not None]
    unarmed_dice=unarmed_profiles[0]['dice'] if selected is None and unarmed_profiles else ''
    if unarmed_dice:weapon=unarmed_dice;weapon_school='str';weapon_proficient=True
    elf_element=definition(c.info.get('elf_element'))
    if rd.get('element_damage') and elf_element:
        effects.append({'stat':'damage','value':rd['element_damage'],'keyword':elf_element.name})
    for e in effects:
        if not e.get('keyword') and e.get('stat') in bonuses:
            bonuses[e['stat']] += e.get('value', 0)
    passive_hp = sum(int(a.data.get('passive_hp',0)) for a in learned)
    extra_hp = int(rd.get('hp_bonus',0)) + passive_hp + sum(e.get('value',0) for e in effects if e.get('stat')=='max_hp')
    max_hp = max(1, extra_hp + int(kd.get('hp_base', 18)) + stats['con'] +
                 (c.level - 1) * (int(kd.get('hp_level', 4)) + mods['con']))
    from .statuses import status_name
    statuses={status_name(e) for e in effects}
    if 'Сбит с ног' in statuses:
        effects.append({'name':'По лежащей цели','stat':'target_hit','value':2,'keyword':'Ближний'})
    if 'Обездвижен' in statuses: bonuses['speed']=-100000
    return {'stats': stats, 'mods': mods, 'sum': sum(stats.values()), 'max_hp': max_hp,
            'ac': max(0, 5 + mods['dex'] + min(5, armor) + other_armor + int(rd.get('ac_bonus',0)) + bonuses['ac']),
            'speed': max(0, int(rd.get('speed', 6)) + bonuses['speed']),
            'hit': bonuses['hit'], 'damage': bonuses['damage'], 'primary': primary,
            'enchantments':enchantments, 'focus_id':focus_id,
            'initiative':mods['dex'] + sum(p.get('initiative',0) for p in enchantments),
            'forced_movement_reduction':sum(p.get('forced_movement_reduction',0) for p in enchantments),
            'massive_strikes':any(a.name=='Массивные удары' and not a.archived for a in c.abilities.all()),
            'weapon_reach':sum(int(m[1]) for word in weapon_words if (m:=re.fullmatch(r'Досягаемость (\d+)',word))),
            'weapon_keywords':weapon_words,
            'versatile':versatile(selected.data) if selected else '',
            'reload_action':reload_action(selected.data) if selected else '',
            'needs_reload':bool(selected and reload_action(selected.data) and selected.data.get('needs_reload')),
            'grip':selected.data.get('grip','one') if selected else 'one',
            'weapon_range_bonus':sum(p.get('range',0) for p in weapon_upgrades),
            'armored_hit':sum(p.get('armored_hit',0) for p in weapon_upgrades),
            'attack_mode':c.runtime.get('attack_mode','melee'),
            'weapon_stat': weapon_school, 'weapon': weapon, 'crit': crit,
            'weapon_hand':selected.data.get('hand','main') if selected else 'main',
            'offhand_penalty':offhand_penalty(selected.data) if selected else 0,
            'weapon_id':weapon_item,'weapon_proficient':weapon_proficient,'weapon_hit':weapon_hit,
            'unarmed_dice':unarmed_dice,'ignore_weapon_requirements':any(p['ignore_requirements'] for p in unarmed_profiles),
            'unarmed':selected is None,'extra_hp':extra_hp,'racial_ac':int(rd.get('ac_bonus',0)),
            'support':support,'support_mastery':support_mastery,
            'step':3 if support=='Воздух' else int(rd.get('step',1)),'resistance':int(rd.get('resistance',0))+(3 if support=='Земля' and support_mastery else 0),
            'skills':skill_values(c,mods,klass),'effects':effects,
            'keywords': keywords, 'reactions': max(1, mods['wis'])*(2 if lightning_reflexes(c) else 1), 'orc': bool(rd.get('orc'))}


def skill_values(c, mods, klass=None):
    background = definition(c.info.get('background_id'))
    automatic = {e.data.get('skill') for e in [klass,background] if e}
    raw = c.info.get('skills', [])
    selected = set(raw if isinstance(raw,list) else [s.strip() for s in raw.split(',')])
    overrides = c.info.get('skill_overrides',{})
    return {name:{'value':mods[stat]+(2 if overrides.get(name,name in selected or name in automatic) else 0),
                  'trained':bool(overrides.get(name,name in selected or name in automatic)), 'stat':stat}
            for name,stat in SKILLS.items()}


def limit(level, circle):
    if not circle:
        return None
    table = {1: (1, 0, 0), 2: (1, 0, 0), 3: (1, 0, 0), 4: (1, 1, 0), 5: (1, 1, 0),
             6: (2, 1, 0), 7: (2, 1, 0), 8: (2, 1, 1), 9: (2, 2, 1), 10: (3, 2, 1)}
    return table[min(10, max(1, level))][min(3, max(1, circle)) - 1]


def formula(c, ability, critical=False, calc=None, scene=None):
    calc = calc or computed(c)
    d = ability.data
    mod_key = d.get('stat') or calc['primary']
    if d.get('weapon'):
        mod_key = calc['weapon_stat']
    result = d.get('formula', '')
    standard = bool(d.get('system')) or ability.name in ['Стандартная атака','Провоцированная атака']
    if standard and calc['unarmed'] and not calc.get('unarmed_dice'):
        result=str(calc['mods']['str'])
    weapon_mod = calc['mods'].get(mod_key,0)
    if standard and not calc['weapon_proficient']:
        weapon_mod = 0
    def weapon(match):
        n = int(match.group(1))
        return re.sub(r'(\d+)[кd](\d+)', lambda m: f'{n * int(m[1])}к{m[2]}', calc['weapon'])
    result = re.sub(r'(\d+)Ор', weapon, result)
    if critical and result:
        factor = 2 + int(d.get('crit', 0)) + (calc['crit'] if d.get('weapon') else 0)
        result = re.sub(r'(\d+)[кd](\d+)', lambda m: f'{int(m[1]) * factor}к{m[2]}', result)
        if calc['orc'] and d.get('weapon') and calc['weapon']:
            result += ' + ' + calc['weapon']
    result = re.sub(r'(\d+)\s*\*?\s*Мод',lambda m:str(int(m[1])*weapon_mod),result)
    result = result.replace('Мод', str(weapon_mod))
    result = re.sub(r'\+\s*-','-',result)
    result = re.sub(r'-\s*-','+',result)
    from .enchantments import for_ability, ability_bonus
    damage = ability_bonus(calc,ability,'damage') + sum(p.get('damage',0) for p in for_ability(calc,ability))
    if calc.get('support')=='Огонь' and int(d.get('circle',0))==0 and d.get('category','active')=='active':
        damage+=calc['mods'][calc['primary']]
    if result and d.get('damage', False) and damage:
        result += f' {damage:+d}'
    from .passives import boulder_bonus
    for contribution in boulder_bonus(c,ability,calc,scene or current_scene(c)):
        if contribution['value']:
            result += f" {contribution['value']:+d} [Земля]"
    return result.strip()


def current_scene(c):
    for scene in Scene.objects.order_by('-id'):
        if scene.state.get('active') and c.id in scene.state.get('order', []):
            return scene
    return None


def availability(c, ability, scene=None, calc=None, readied=False, as_reaction=False):
    calc = calc or computed(c)
    d = ability.data
    category = d.get('category', 'active')
    if category == 'passive':
        return 'Пассивное умение'
    if category == 'noncombat':
        return 'Только вне боя' if scene else ''
    if not scene:
        return 'Начните бой'
    from .stances import sphere_profile, mode
    if sphere_profile(ability) is not None and not mode(c):return 'Сначала активируйте Стихийную поддержку'
    if getattr(ability,'name','')=='Передача истощения':
        from .prepared_attacks import exhaustion
        if not exhaustion(c):return 'Нет истощения маны для передачи'
    if getattr(ability,'name','')=='Ищущие стрелы':
        from .seeking_arrows import reason
        blocked=reason(c,scene,calc)
        if blocked:return blocked
    from .statuses import status_name
    statuses={status_name(e) for e in c.runtime.get('effects',[])}
    if statuses.intersection({'Сон','Страх'}):
        return 'Персонаж пропускает ход: '+', '.join(statuses.intersection({'Сон','Страх'}))
    action = d.get('action', 'main')
    if as_reaction:
        from .passives import reflex_reason
        blocked=reflex_reason(c,ability,scene)
        if blocked:return blocked
        if readied:return 'Отложенное действие нельзя одновременно применять через рефлексы'
        action='reaction'
    if readied:
        from .readied import reason
        blocked=reason(c,scene,action,readied if isinstance(readied,str) else None)
        if blocked:return blocked
    if c.runtime.get('stun_pending',0) and scene.state['order'][scene.state['turn']]==c.id:
        return 'Оглушение: выберите пропускаемые действия'
    if action == 'reaction' and scene.state['order'][scene.state['turn']] == c.id:
        return 'Реакция доступна на чужом ходу'
    if not readied and action not in ['reaction','free'] and scene.state['order'][scene.state['turn']] != c.id:
        return 'Ход другого персонажа'
    if not readied and action != 'free' and c.runtime.get('actions', {}).get(action, 0) < 1:
        return 'Нет нужного действия'
    count = limit(c.level, int(d.get('circle', 0)))
    if count is not None and c.runtime.get('used', {}).get(str(ability.id), 0) >= count:
        return 'Применения закончились'
    if d.get('weapon') and not calc['weapon'] and not d.get('system') and ability.name!='Стандартная атака':
        return 'Нужно оружие в руках'
    if d.get('weapon') and calc.get('needs_reload'):
        return 'Перезарядите оружие'
    required = d.get('requires', [])
    if required and not set(required).intersection(calc['keywords']) and not (d.get('weapon') and calc.get('ignore_weapon_requirements')):
        return 'Нужно подходящее оружие'
    return ''


def put_effect(c, effect):
    existing = c.runtime.setdefault('effects', [])
    # Same named status: strongest magnitude, renewed target-turn duration.
    for old in existing:
        if old['key'] == effect['key']:
            effect['value'] = old['value'] if abs(old['value'])>abs(effect['value']) else effect['value']
            existing.remove(old)
            break
    existing.append(effect)


ITEM_FIELDS = ['character_id','campaign_id','entry_id','name','quantity','equipped','slot','data','archived']


def item_snapshot(item):
    return {key:getattr(item,key) for key in ITEM_FIELDS}


class Change:
    """Store only changed resource snapshots. Undo never replaces unrelated resources."""
    def __init__(self, user, label, scene=None, inputs=None):
        self.user, self.label, self.scene = user, label, scene
        self.objects = {}
        self.before = {}
        self.inputs = copy.deepcopy(inputs or {})
        if scene:self.depend(scene)

    def watch(self, obj):
        key = ('scene:' if isinstance(obj, Scene) else 'item:' if isinstance(obj,Item) else 'character:') + str(obj.pk)
        if key not in self.objects:
            self.objects[key] = obj
            self.before[key] = copy.deepcopy(item_snapshot(obj) if isinstance(obj,Item) else obj.state if isinstance(obj, Scene) else obj.runtime)
        return obj

    def action(self, character, action):
        from .periodic import action_performed
        action_performed(self, character, action)

    def depend(self, obj):
        key=('scene:' if isinstance(obj,Scene) else 'item:' if isinstance(obj,Item) else 'character:')+str(obj.pk)
        self.inputs.setdefault('dependencies',[])
        if key not in self.inputs['dependencies']:self.inputs['dependencies'].append(key)

    def absorb(self, other):
        for key,obj in other.objects.items():
            self.before.setdefault(key,other.before[key])
            self.objects[key]=obj
        for key in other.inputs.get('dependencies',[]):
            if key not in self.inputs.setdefault('dependencies',[]):self.inputs['dependencies'].append(key)

    def finish(self, record=False, defer_record=False):
        after = {}
        for key, obj in self.objects.items():
            value = item_snapshot(obj) if isinstance(obj,Item) else obj.state if isinstance(obj, Scene) else obj.runtime
            if value != self.before[key]:
                after[key] = copy.deepcopy(value)
                if isinstance(obj,Item):
                    obj.revision+=1
                    obj.save(update_fields=ITEM_FIELDS+['revision'])
                else:obj.save(update_fields=['state'] if isinstance(obj, Scene) else ['runtime'])
        if not defer_record and (after or record):
            Event.objects.filter(actor=self.user, undone=True).update(redoable=False)
            Event.objects.create(actor=self.user, label=self.label, scene=self.scene,
                                 before={k: self.before[k] for k in after}, after=after, inputs=self.inputs)


def rolls_required(ability):
    if ability.data.get('rolls') is not None:
        return bool(ability.data['rolls'])
    return bool(re.search(r'(?:\d+\s*)?[кd]\s*\d+', ability.data.get('formula', '') + ' ' + ability.description, re.I))


def undo(user, redo=False):
    events = Event.objects.filter(actor=user, undone=redo)
    if redo:
        events = events.filter(redoable=True).order_by('id')
    else:
        events = events.order_by('-id')
    event = events.first()
    if not event:
        raise ValueError('Нет действия для повтора' if redo else 'Нет действия для отмены')
    keys = set(event.after)
    for later in Event.objects.filter(id__gt=event.id, undone=False):
        if keys.intersection(set(later.after)|set(later.inputs.get('dependencies',[]))):
            raise ValueError('Отмена зависит от более позднего действия: ' + later.label)
    expected = event.before if redo else event.after
    replacement = event.after if redo else event.before
    objects = []
    for key in keys:
        kind, pk = key.split(':')
        obj = (Scene if kind == 'scene' else Item if kind=='item' else Character).objects.get(pk=pk)
        if kind=='item':
            if any(getattr(obj,k)!=v for k,v in expected[key].items()):
                raise ValueError('Предмет изменился. Сначала отмените зависимые действия.')
            objects.append((obj,None,replacement[key]))
        else:
            attr='state' if kind=='scene' else 'runtime'
            if getattr(obj,attr)!=expected[key]:raise ValueError('Состояние изменилось. Сначала отмените зависимые действия.')
            objects.append((obj,attr,replacement[key]))
    for obj, attr, value in objects:
        if isinstance(obj,Item):
            for k,v in value.items():setattr(obj,k,v)
            obj.revision+=1;obj.save(update_fields=list(value)+['revision'])
        else:
            setattr(obj,attr,value);obj.save(update_fields=[attr])
    event.undone = not redo
    event.save(update_fields=['undone'])
