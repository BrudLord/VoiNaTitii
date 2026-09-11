"""Character choices extracted from the race and class chapters."""
import re

SCHOOL_NAMES = dict(zip(
    ['Изначальной', 'Огня', 'Воды', 'Земли', 'Воздуха', 'Тьмы', 'Света', 'Молнии', 'Холода', 'Природы',
     'Арбалета', 'Лука', 'Меча', 'Копья', 'Булавы', 'Цепа', 'Кинжала', 'Молота', 'Древкового', 'Топора', 'Щита'],
    ['Изначальная', 'Огонь', 'Вода', 'Земля', 'Воздух', 'Тьма', 'Свет', 'Молния', 'Холод', 'Природа',
     'Арбалеты', 'Луки', 'Мечи', 'Копья', 'Булавы', 'Цепы', 'Кинжалы', 'Молоты', 'Древковое', 'Топоры', 'Щиты']))


def book_choices(text):
    result = {}
    for chapter, kind in [(2, 'race'), (3, 'class')]:
        section = text.split(f'## Глава {chapter}.', 1)[1].split('## Глава ', 1)[0]
        for match in re.finditer(r'^### ([^\n]+)\n(.*?)(?=^### |\Z)', section, re.M | re.S):
            name, body = match[1].strip(), match[2]
            if kind == 'race':
                data = {'subraces': re.findall(r'^#### ([^\n]+)', body, re.M)}
            else:
                line = re.search(r'^\*\*Школы:\*\* (.+)', body, re.M)
                if not line:
                    raise ValueError(f'Нет списка школ класса {name}')
                names = re.findall(r'\[\*\*([^*]+)\*\*\]', line[1])
                if not names or any(n not in SCHOOL_NAMES for n in names):
                    raise ValueError(f'Неизвестная школа класса {name}: {names}')
                data = {'allowed_schools': [SCHOOL_NAMES[n] for n in names]}
            result[(kind, name)] = data
    return result
