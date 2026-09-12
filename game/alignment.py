"""Chapter 8's diagram, including conditional dotted transitions.

Source: rules/player-book.txt, chapter 8 and linked image
https://i.ibb.co/gZBWzL5Q/image.png (visually checked).
"""
PAIRS = [('Личное', 'Общее'), ('Свобода', 'Необходимость'), ('Хаос', 'Порядок')]
JOINT = {
    'Независимость': ('Личное', 'Свобода'),
    'Творчество': ('Свобода', 'Хаос'),
    'Равенство': ('Хаос', 'Общее'),
    'Коллектив': ('Общее', 'Необходимость'),
    'Закон': ('Необходимость', 'Порядок'),
    'Статус': ('Порядок', 'Личное'),
}
DOTTED = {'Эгоизм':'Личное', 'Решимость':'Свобода', 'Интуиция':'Хаос',
          'Альтруизм':'Общее', 'Адаптация':'Необходимость', 'Система':'Порядок'}


def available_priorities(values, extra=''):
    selected = set(values) | ({extra} if extra else set())
    joint = {name for name, pair in JOINT.items() if set(pair) <= selected}
    used = {value for name in joint for value in JOINT[name]}
    # Dotted is allowed only when that inner value has no available solid transition.
    return joint | {name for name,value in DOTTED.items() if value in selected and value not in used}


def validate_alignment(info):
    values = info.get('alignment_values') or []
    if not isinstance(values,list) or len(values)>3:
        raise ValueError('Выберите по одной ценности из трёх пар')
    values = values + ['']*(3-len(values))
    if any(value and value not in pair for value,pair in zip(values,PAIRS)):
        raise ValueError('Выберите по одной ценности из каждой пары')
    extra = info.get('alignment_extra') or ''
    if extra and (extra not in sum((list(p) for p in PAIRS),[]) or extra in values):
        raise ValueError('Дополнительная ценность должна отличаться от основных')
    if extra and not all(values):
        raise ValueError('Сначала выберите три основные ценности')
    return available_priorities(values,extra)


def schema():
    return {'pairs':PAIRS,'joint':JOINT,'dotted':DOTTED}
