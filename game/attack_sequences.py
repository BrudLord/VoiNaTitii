"""Validate ordered physical attack results without spending any game resources.

The executor can replay these steps against the state produced by the preceding
step, then record the entire ability as one Change. External targets are labels,
not monster records or hit point models.
"""
import copy
from collections import Counter


BOOK = {
    'Быстрые уколы': {'count': 3, 'targets': 'same'},
    'Скрытый удар': {'count': 2, 'targets': 'same'},
    'Захват пространства': {'count': 3, 'minimum': 1, 'targets': 'any', 'step_after_attack': 1},
    'Шквал ударов': {'count': 2, 'targets': 'each'},
    'Осколки тьмы': {'count': 2, 'targets': 'any'},
    'Серия выстрелов': {'count': 3, 'targets': 'different'},
    'Тормозящие стрелы': {'count': 2, 'targets': 'same'},
    'Стрельба на ходу': {'count': 2, 'targets': 'any', 'during_movement': True},
    'Стрельба навесом': {'count': 2, 'targets': 'each'},
    'Направленный залп': {'count': 5, 'minimum': 1, 'targets': 'any', 'one_per_step': True},
}
TARGETS = {'same', 'any', 'different', 'each'}
OUTCOMES = {'hit', 'miss', 'critical'}


def validate_profile(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {
        'count', 'minimum', 'targets', 'step_after_attack', 'during_movement', 'one_per_step'
    }:
        raise ValueError('Некорректные параметры последовательности атак')
    count, minimum = value.get('count'), value.get('minimum', value.get('count'))
    if type(count) is not int or not 1 <= count <= 100 or type(minimum) is not int or not 1 <= minimum <= count:
        raise ValueError('Укажите допустимое количество атак')
    if not isinstance(value.get('targets'), str) or value['targets'] not in TARGETS:
        raise ValueError('Выберите правило выбора целей серии')
    if 'step_after_attack' in value and (type(value['step_after_attack']) is not int or not 1 <= value['step_after_attack'] <= 100):
        raise ValueError('Укажите длину шага после атаки')
    for key in ['during_movement', 'one_per_step']:
        if key in value and type(value[key]) is not bool:
            raise ValueError('Параметр движения должен быть отметкой')
    if value.get('one_per_step') and value['targets'] == 'each':
        raise ValueError('Выстрел за клетку не задаёт серию на каждого получателя')
    return copy.deepcopy(value)


def profile(ability):
    # Explicit null disables the profile; an edited name never restores it.
    if 'attack_sequence' in ability.data:
        return validate_profile(ability.data['attack_sequence'])
    return copy.deepcopy(BOOK.get(ability.name))


def standard_count(ability):
    value=ability.data.get('standard_attack_count',2 if ability.name=='Стремительные удары' else None)
    if value is not None and (type(value) is not int or not 1<=value<=100):
        raise ValueError('Количество стандартных атак должно быть целым числом от 1 до 100')
    return value


def effective_profile(ability,character):
    """Keep an explicit attack profile; otherwise derive the learned passive.

    This is an ability's attack count, not extra actions or extra uses. Duplicate
    versions of the passive never multiply one another.
    """
    existing=profile(ability)
    if 'attack_sequence' in ability.data or existing is not None:return existing
    if ability.name!='Стандартная атака' or not ability.data.get('system'):return None
    count=max((standard_count(a) or 1 for a in character.abilities.all()
               if not a.archived and a.data.get('category','active')=='passive'),default=1)
    return {'count':count,'targets':'any'} if count>1 else None


def target_key(row, participants):
    pk = row.get('target')
    external = row.get('external_target', '')
    if not isinstance(external, str):
        raise ValueError('Название противника должно быть текстом')
    if pk is not None:
        if type(pk) is not int or pk not in participants or external:
            raise ValueError('Выберите участника боя или назовите противника на поле')
        return ('character', pk)
    if not isinstance(external, str) or not external.strip() or len(external.strip()) > 120:
        raise ValueError('Назовите противника на поле для каждой атаки')
    return ('external', ' '.join(external.split()).casefold().replace('ё', 'е'))


def plan(ability, payload, participants, *, multiplier=1, character=None):
    """Return immutable-by-convention steps; never alter rows or model instances.

    multiplier is executor-owned (e.g. a consumed Quick Fire preparation), never
    accepted from payload. Count and same/different-target rules are independent
    of hit/miss: a miss is still an attack against the selected target.
    """
    spec = effective_profile(ability,character) if character is not None else profile(ability)
    if not spec:
        raise ValueError('У этого умения нет последовательности атак')
    if type(multiplier) is not int or multiplier not in [1, 2]:
        raise ValueError('Некорректный множитель количества атак')
    rows = payload.get('attacks')
    if not isinstance(rows, list) or not rows or len(rows) > 1000:
        raise ValueError('Укажите атаки последовательности')
    steps, keys = [], []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError('Некорректная атака в последовательности')
        key = target_key(row, participants)
        outcome = row.get('outcome')
        if not isinstance(outcome, str) or outcome not in OUTCOMES:
            raise ValueError('Укажите попадание, промах или крит каждой атаки')
        if ability.data.get('automatic_hit') and outcome == 'miss':
            raise ValueError('Автоматическое попадание не может промахнуться')
        roll = row.get('roll_result')
        if not isinstance(roll, str) or not roll.strip() or len(roll) > 2000:
            raise ValueError('Введите результат физического броска каждой атаки')
        steps.append({**copy.deepcopy(row), 'number': index + 1, 'roll_result': roll.strip(),
                      'target': key[1] if key[0] == 'character' else None,
                      'external_target': row.get('external_target', '').strip()})
        keys.append(key)
    count, minimum = spec['count'] * multiplier, spec.get('minimum', spec['count']) * multiplier
    if spec['targets'] == 'each':
        if any(n != count for n in Counter(keys).values()):
            raise ValueError(f'Для каждого получателя укажите {count} атаки')
    elif not minimum <= len(steps) <= count:
        raise ValueError(f'Количество атак должно быть от {minimum} до {count}')
    if spec['targets'] == 'same' and len(set(keys)) != 1:
        raise ValueError('Все атаки этого умения направлены в одну цель')
    if spec['targets'] == 'different' and len(set(keys)) != len(keys):
        raise ValueError('Выберите разные цели для каждой атаки')
    if spec.get('one_per_step'):
        distance = payload.get('steps')
        if type(distance) is not int or not 1 <= distance <= spec['count'] or len(steps) != distance * multiplier:
            raise ValueError('Количество выстрелов должно соответствовать пройденным клеткам')
    return {'profile': spec, 'attacks': steps, 'all_missed': all(row['outcome'] == 'miss' for row in steps),
            'successful_targets': list(dict.fromkeys(key for key, row in zip(keys, steps) if row['outcome'] != 'miss'))}


# A step may describe an attack, but cannot impersonate another actor, change the
# ability, reserve a second action, or recursively inject another sequence.
STEP_FIELDS = {
    'number', 'target', 'external_target', 'outcome', 'roll_result', 'reactions',
    'reaction_rolls', 'spreads', 'external_bp', 'external_conductor', 'external_prone',
    'mark_source_included', 'mystic_arrows', 'charged_arrows', 'charged_target',
    'exhaustion_target', 'miss_damage', 'movement_before', 'movement_after', 'weave', 'reload_before', 'draw_weapon',
}


def move_step(change, character, step, spec, spent, phase):
    from .movement import resolve
    from .rules import computed
    movement = step.get('movement_' + phase)
    if spec.get('one_per_step') and phase == 'before':
        movement = movement or {'cells': 1, 'cell_cost': 1}
        if not isinstance(movement, dict) or movement.get('cells') != 1:
            raise ValueError('Перед каждым выстрелом залпа нужно пройти одну клетку')
    if movement is None:
        return spent
    if not isinstance(movement, dict):
        raise ValueError('Укажите путь шага')
    calc = computed(character)
    if spec.get('during_movement'):
        limit = max(0, calc['speed'] - spent)
    elif spec.get('step_after_attack') and phase == 'after':
        limit = spec['step_after_attack']
    elif spec.get('one_per_step') and phase == 'before':
        limit = 1
    else:
        raise ValueError('Это умение не даёт шага в выбранный момент')
    result, sources = resolve(character, {**movement, 'mode': 'step'}, change.scene, calc, step_limit=limit)
    for source in sources:
        change.depend(source)
    step.setdefault('_movement_log', []).append({**result, 'phase': phase})
    return spent + result['cells']


def execute(user, payload, character, ability, scene, *, drawn=None, embedded=False, preview_steps=None):
    """Execute a validated sequence inside the action endpoint's transaction.

    Intermediate changes are persisted for the next attack's calculations but
    generate no events. The encompassing Change owns the original snapshots.
    """
    from .views import use_ability
    from .rules import Change
    from .passives import turn_token
    if payload.get('op') != 'ability.use' or not (ability.data.get('damage') or ability.data.get('weapon')):
        raise ValueError('Последовательность должна состоять из атак')
    ordered = plan(ability, payload, set(scene.state['order']),character=character)
    if preview_steps is not None and (type(preview_steps) is not int or not 0 <= preview_steps <= len(ordered['attacks'])):
        raise ValueError('Некорректный номер атаки для предварительного расчёта')
    for step in ordered['attacks']:
        if set(step) - STEP_FIELDS:
            raise ValueError('В атаке серии есть неподдерживаемые параметры')
    change = drawn or Change(user, ability.display_name + ' · ' + character.name, scene)
    change.label = ability.display_name + ' · ' + character.name
    change.watch(character)
    action = 'reaction' if payload.get('as_reaction') else ability.data.get('action', 'main')
    if not embedded:
        change.action(character, action)
    if action != 'free' and not payload.get('use_ready'):
        character.runtime['actions'][action] -= 1
    change.inputs['attack_sequence'] = {'attacks': [], 'profile': ordered['profile']}
    change.inputs['outcome'] = 'miss' if ordered['all_missed'] else 'hit'
    if payload.get('support_minor'):
        change.label += ' · Малым'
        change.inputs['support_minor'] = True
    if payload.get('as_reaction'):
        change.label = 'Молниеносные рефлексы · ' + change.label
        character.runtime.setdefault('once_per_turn', {})['lightning_reflexes'] = turn_token(scene)
        change.inputs['as_reaction'] = True
    # Charged Arrows belongs to this whole ability. Each attack can assign its
    # own Ор slots; the preparation disappears once, after the final attack.
    charged = copy.deepcopy(character.runtime.get('charged_arrows'))
    change.finish(defer_record=True)
    moved = 0
    executed = ordered['attacks'] if preview_steps is None else ordered['attacks'][:preview_steps]
    for index, step in enumerate(executed):
        current = change.objects['character:' + str(character.pk)]
        reloaded=None
        if 'reload_before' in step:
            if type(step['reload_before']) is not bool:raise ValueError('Подтвердите перезарядку')
            if step['reload_before']:
                from .weaponry import reload_weapon
                from .rules import computed
                if not ability.data.get('weapon'):raise ValueError('Перезарядка доступна перед атакой оружием')
                reload_change=reload_weapon(user,{'character':character.pk,'item':computed(current)['weapon_id']},embedded=True)
                change.absorb(reload_change);reloaded=reload_change.inputs
                change.inputs.setdefault('periodic_damage',[]).extend(reloaded.get('periodic_damage',[]))
                current=change.objects['character:' + str(character.pk)]
        moved = move_step(change, current, step, ordered['profile'], moved, 'before')
        args = {k: copy.deepcopy(v) for k, v in step.items() if k not in {'number', 'target', 'external_target', 'movement_before', 'movement_after', '_movement_log', 'reload_before'}}
        args.update(op='ability.use', character=character.pk, ability=ability.pk,
                    targets=[] if step['target'] is None else [step['target']],
                    support_minor=bool(payload.get('support_minor')))
        try:
            child = use_ability(user, args, embedded=embedded, sequence_step=True)
        except ValueError as error:
            raise ValueError(f'Атака {index + 1}: {error}') from error
        if step['external_target']:
            for row in child.inputs.get('attack_targets', []):
                row['name'] = step['external_target']
        change.absorb(child)
        current = change.objects['character:' + str(character.pk)]
        if charged and index + 1 < len(ordered['attacks']):
            current.runtime['charged_arrows'] = copy.deepcopy(charged)
        child.finish(defer_record=True)
        moved = move_step(change, current, step, ordered['profile'], moved, 'after')
        change.inputs['attack_sequence']['attacks'].append({
            'number': index + 1, 'target': step['target'], 'external_target': step['external_target'],
            'inputs': copy.deepcopy(child.inputs), 'movement': step.get('_movement_log', []),
            **({'reload':reloaded} if reloaded else {}),
        })
    current = change.objects['character:' + str(character.pk)]
    # Keep the existing journal useful while preserving full per-step metadata
    # for the sequence editor and detailed replay.
    change.inputs['roll_result'] = ' · '.join(f"{step['number']}: {step['roll_result']}" for step in executed)
    change.inputs['attack_targets'] = [
        {**row, 'name': f"Атака {step['number']} · {row['name']}"}
        for step in change.inputs['attack_sequence']['attacks']
        for row in step['inputs'].get('attack_targets', [])
    ]
    if preview_steps is not None:
        if not executed:change.inputs['outcome'] = None
        return change
    if not (ordered['all_missed'] and ability.data.get('reliable')):
        used = current.runtime.setdefault('used', {})
        used[str(ability.pk)] = used.get(str(ability.pk), 0) + 1
    if payload.get('use_ready'):
        from .readied import resolve
        resolve(change, current, scene, payload, ability.data.get('action', 'main'))
    if embedded:
        return change
    change.finish()
    return change
