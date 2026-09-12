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


def plan(ability, payload, participants, *, multiplier=1):
    """Return immutable-by-convention steps; never alter rows or model instances.

    multiplier is executor-owned (e.g. a consumed Quick Fire preparation), never
    accepted from payload. Count and same/different-target rules are independent
    of hit/miss: a miss is still an attack against the selected target.
    """
    spec = profile(ability)
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
