import copy
import re
from .models import Character, Entry, Event, Scene

STATS = [('str', 'Сила'), ('dex', 'Ловкость'), ('con', 'Телосложение'),
         ('int', 'Интеллект'), ('wis', 'Мудрость'), ('cha', 'Харизма')]
ACTIONS = {'main': 1, 'minor': 1, 'move': 1}


def fresh():
    return {'hp': 0, 'temp': 0, 'used': {}, 'actions': dict(ACTIONS), 'effects': [], 'turns': 0}


def definition(pk):
    return Entry.objects.filter(pk=pk).first() if str(pk).isdigit() else None


def computed(c):
    stats = {k: int(c.stats.get(k, 10)) for k, _ in STATS}
    effects = list(c.runtime.get('effects', []))
    for ability in c.abilities.all():
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
    bonuses = {'ac': 0, 'speed': 0, 'hit': 0, 'damage': 0}
    keywords = []
    weapon = '1к4'
    weapon_school = primary
    crit = 0
    for item in c.items.filter(equipped=True):
        armor += int(item.data.get('armor', 0))
        keywords += item.data.get('keywords', [])
        if item.data.get('dice'):
            weapon = item.data['dice']
            weapon_school = item.data.get('stat', primary)
            crit += int(item.data.get('crit', 0))
    for e in effects:
        if not e.get('keyword') and e.get('stat') in bonuses:
            bonuses[e['stat']] += e.get('value', 0)
    max_hp = max(1, int(kd.get('hp_base', 18)) + stats['con'] +
                 (c.level - 1) * (int(kd.get('hp_level', 4)) + mods['con']))
    return {'stats': stats, 'mods': mods, 'sum': sum(stats.values()), 'max_hp': max_hp,
            'ac': max(0, 5 + mods['dex'] + min(5, armor) + bonuses['ac']),
            'speed': max(0, int(rd.get('speed', 6)) + bonuses['speed']),
            'hit': bonuses['hit'], 'damage': bonuses['damage'], 'primary': primary,
            'weapon_stat': weapon_school, 'weapon': weapon, 'crit': crit,
            'keywords': keywords, 'reactions': max(1, mods['wis']), 'orc': bool(rd.get('orc'))}


def limit(level, circle):
    if not circle:
        return None
    table = {1: (1, 0, 0), 2: (1, 0, 0), 3: (1, 0, 0), 4: (1, 1, 0), 5: (1, 1, 0),
             6: (2, 1, 0), 7: (2, 1, 0), 8: (2, 1, 1), 9: (2, 2, 1), 10: (3, 2, 1)}
    return table[min(10, max(1, level))][min(3, max(1, circle)) - 1]


def formula(c, ability, critical=False):
    calc = computed(c)
    d = ability.data
    mod_key = d.get('stat') or calc['primary']
    if d.get('weapon'):
        mod_key = calc['weapon_stat']
    result = d.get('formula', '')
    def weapon(match):
        n = int(match.group(1))
        return re.sub(r'(\d+)[кd](\d+)', lambda m: f'{n * int(m[1])}к{m[2]}', calc['weapon'])
    result = re.sub(r'(\d+)Ор', weapon, result)
    if critical and result:
        factor = 2 + int(d.get('crit', 0)) + (calc['crit'] if d.get('weapon') else 0)
        result = re.sub(r'(\d+)[кd](\d+)', lambda m: f'{int(m[1]) * factor}к{m[2]}', result)
        if calc['orc'] and d.get('weapon'):
            result += ' + ' + calc['weapon']
    result = result.replace('Мод', str(calc['mods'].get(mod_key, 0)))
    damage = calc['damage']
    for e in c.runtime.get('effects', []):
        if e.get('keyword') in d.get('keywords', []) and e.get('keyword') and e.get('stat') == 'damage':
            damage += e.get('value', 0)
    if result and d.get('damage', False) and damage:
        result += f' {damage:+d}'
    return result


def current_scene(c):
    for scene in Scene.objects.order_by('-id'):
        if scene.state.get('active') and c.id in scene.state.get('order', []):
            return scene
    return None


def availability(c, ability, scene=None):
    d = ability.data
    category = d.get('category', 'active')
    if category == 'passive':
        return 'Пассивное умение'
    if category == 'noncombat':
        return 'Только вне боя' if scene else ''
    if not scene:
        return 'Начните бой'
    action = d.get('action', 'main')
    if action != 'reaction' and scene.state['order'][scene.state['turn']] != c.id:
        return 'Ход другого персонажа'
    if action != 'free' and c.runtime.get('actions', {}).get(action, 0) < 1:
        return 'Нет нужного действия'
    count = limit(c.level, int(d.get('circle', 0)))
    if count is not None and c.runtime.get('used', {}).get(str(ability.id), 0) >= count:
        return 'Применения закончились'
    required = d.get('requires', [])
    if required and not set(required).intersection(computed(c)['keywords']):
        return 'Нужно подходящее оружие'
    return ''


def put_effect(c, effect):
    existing = c.runtime.setdefault('effects', [])
    # Same named status: strongest magnitude, renewed target-turn duration.
    for old in existing:
        if old['key'] == effect['key']:
            effect['value'] = max(old['value'], effect['value'])
            existing.remove(old)
            break
    existing.append(effect)


class Change:
    """Store only changed resource snapshots. Undo never replaces unrelated resources."""
    def __init__(self, user, label, scene=None, inputs=None):
        self.user, self.label, self.scene = user, label, scene
        self.objects = {}
        self.before = {}
        self.inputs = inputs or {}

    def watch(self, obj):
        key = ('scene:' if isinstance(obj, Scene) else 'character:') + str(obj.pk)
        if key not in self.objects:
            self.objects[key] = obj
            self.before[key] = copy.deepcopy(obj.state if isinstance(obj, Scene) else obj.runtime)
        return obj

    def finish(self):
        after = {}
        for key, obj in self.objects.items():
            value = obj.state if isinstance(obj, Scene) else obj.runtime
            if value != self.before[key]:
                after[key] = copy.deepcopy(value)
                obj.save(update_fields=['state'] if isinstance(obj, Scene) else ['runtime'])
        if after:
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
        if keys.intersection(later.after):
            raise ValueError('Отмена зависит от более позднего действия: ' + later.label)
    expected = event.before if redo else event.after
    replacement = event.after if redo else event.before
    objects = []
    for key in keys:
        kind, pk = key.split(':')
        obj = (Scene if kind == 'scene' else Character).objects.get(pk=pk)
        attr = 'state' if kind == 'scene' else 'runtime'
        if getattr(obj, attr) != expected[key]:
            raise ValueError('Состояние изменилось. Сначала отмените зависимые действия.')
        objects.append((obj, attr, replacement[key]))
    for obj, attr, value in objects:
        setattr(obj, attr, value)
        obj.save(update_fields=[attr])
    event.undone = not redo
    event.save(update_fields=['undone'])
