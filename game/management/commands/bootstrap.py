import os
import re
from pathlib import Path
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.conf import settings
from game.models import Entry, Clock

SCHOOL = {'Изначальная': 'int', 'Огонь': 'int', 'Вода': 'wis', 'Земля': 'wis', 'Воздух': 'int',
          'Тьма': 'cha', 'Свет': 'cha', 'Молния': 'int', 'Холод': 'wis', 'Природа': 'cha',
          'Арбалеты': 'con', 'Луки': 'dex', 'Мечи': 'dex', 'Копья': 'str', 'Булавы': 'str',
          'Цепы': 'con', 'Кинжалы': 'dex', 'Молоты': 'str', 'Древковое': 'dex', 'Топоры': 'str', 'Щиты': 'con'}
SCHOOL_TITLES = dict(zip(['Изначальной', 'Огня', 'Воды', 'Земли', 'Воздуха', 'Тьмы', 'Света', 'Молнии',
                         'Холода', 'Природы', 'Арбалета', 'Лука', 'Меча', 'Копья', 'Булавы', 'Цепа',
                         'Кинжала', 'Молота', 'Древкового', 'Топора', 'Щита'], SCHOOL))


class Command(BaseCommand):
    help = 'Первичная загрузка книги и мастера. Существующие записи и пароль не меняются.'

    def handle(self, **options):
        Clock.objects.get_or_create(pk=1)
        if not User.objects.filter(username='admin').exists():
            password = os.getenv('ADMIN_INITIAL_PASSWORD')
            if not password:
                raise ValueError('Передайте ADMIN_INITIAL_PASSWORD для первого запуска')
            User.objects.create_superuser('admin', password=password)
        text = (settings.BASE_DIR / 'rules/player-book.txt').read_text()
        def add(kind, name, desc='', data=None, source='Книга игрока'):
            return Entry.objects.get_or_create(kind=kind, name=name, defaults={'description': desc,
                       'data': data or {}, 'source': source})[0]
        for name, stat in SCHOOL.items():
            add('school', name, data={'stat': stat})
        for chapter, kind in [(2, 'race'), (3, 'class'), (8, 'background'), (10, 'specialization')]:
            section = text.split(f'## Глава {chapter}.', 1)[1].split('## Глава ', 1)[0]
            for m in re.finditer(r'^### ([^\n]+)\n(.*?)(?=^### |\Z)', section, re.S | re.M):
                name, desc = m[1].strip(), m[2]
                if kind == 'background' and name in ['Мировоззрение', 'Приоритеты']:
                    continue
                data = {}
                if kind == 'class':
                    base = re.search(r'Хиты на первом уровне:\*\*\s*(\d+)', desc)
                    growth = re.search(r'Хиты на следующих уровнях:\*\*\s*(\d+)', desc)
                    if base: data['hp_base'] = int(base[1])
                    if growth: data['hp_level'] = int(growth[1])
                if kind == 'race':
                    speed = re.search(r'Скорость\s+(\d+)', desc)
                    data = {'speed': int(speed[1]) if speed else 6, 'orc': name == 'Орк'}
                clean = re.sub(r'!\[[^\]]*\]\([^)]*\)[^\n]*|<[^>]*>|\\(?:page|column)|\{\{[^\n]*|\}\}', '', desc)
                add(kind, name, clean[:15000], data)
        for m in re.finditer(r'\{\{monster,frame\s*\n##### ([^\n]+)\n(.*?)\n\}\}', text, re.S):
            before = text[:m.start()]
            chapter = re.findall(r'^## Глава (\d+)\.', before, re.M)[-1]
            headings = re.findall(r'^### ([^\n]+)', before, re.M)
            source = headings[-1] if headings else 'Книга'
            body = m[2].strip()
            parts = body.split('___')
            keys = re.sub(r'[*\n]', '', parts[1]).strip() if len(parts) > 2 else ''
            desc = parts[-1].strip() if len(parts) > 2 else body
            heading_positions = list(re.finditer(r'^### [^\n]+', before, re.M))
            recent = before[heading_positions[-1].start():] if heading_positions else before
            circle_match = re.findall(r'^##### ([123]) круг', recent, re.M)
            circle = int(circle_match[-1]) if circle_match else 0
            # Class sections mark non-combat abilities before class values.
            category = 'noncombat' if chapter in ['8', '9'] or (chapter == '3' and
                       before.rfind('##### Небоевое умение') > before.rfind('#### Классовые значения')) else 'active'
            if 'Пассивный' in keys and category == 'active': category = 'passive'
            action = next((v for k, v in [('Малым', 'minor'), ('Свободным', 'free'), ('Реакция', 'reaction'), ('Движение', 'move')] if k in keys), 'main')
            data = {'category': category, 'circle': circle, 'action': action, 'keywords': [k.strip() for k in keys.split(',') if k.strip()],
                    'source_name': source, 'manual': True}
            if source.startswith('Школа '):
                name = SCHOOL_TITLES.get(source.removeprefix('Школа '))
                if name: data['stat'] = SCHOOL[name]
            add('ability', m[1].strip(), desc, data, f'Книга, строка {text[:m.start()].count(chr(10)) + 1}')
        # These reviewed definitions have executable effects. Existing user edits are preserved.
        reviewed = {
            'Благословение': {'category': 'active', 'action': 'main', 'circle': 1, 'target': 'single', 'stat': 'cha',
                'source_name': 'Школа Света', 'keywords': ['Дальнобойный 5', 'Свет'], 'effects': [
                {'name': 'Благословение 2', 'key': 'blessing', 'stat': 'hit', 'value': 2, 'turns': 3},
                {'stat': 'temp', 'value': 5}, {'name': 'Благословение: урон', 'key': 'blessing-damage', 'stat': 'damage', 'value': 1, 'duration': 'battle'}]},
            'Солнечный луч': {'category': 'active', 'action': 'main', 'circle': 0, 'stat': 'cha', 'damage': True,
                'formula': '1к6 + Мод', 'source_name': 'Школа Света', 'keywords': ['Линия 4', 'Свет']},
            'Исцеление': {'category': 'active', 'action': 'main', 'circle': 1, 'stat': 'cha', 'formula': '3к6 + 2 × Мод',
                'source_name': 'Школа Света', 'keywords': ['Ближний'], 'manual': True},
            'Стандартная атака': {'category': 'active', 'action': 'main', 'circle': 0, 'formula': '1Ор + Мод',
                'weapon': True, 'damage': True, 'keywords': ['Оружие', 'Ближний']},
        }
        for name, data in reviewed.items():
            a = add('ability', name, 'Стандартная атака оружием.' if name == 'Стандартная атака' else '')
            if a.data.get('manual') or not a.data:
                if not a.data.get('reviewed'):
                    a.data = {**data, 'reviewed': True}
                    a.save()
        # A configurable aura example, explicitly distinct from book content.
        add('ability', 'Учебная аура защиты', 'Пример настройки ауры: +1 КД выбранным союзникам. Мастер может изменить или удалить.',
            {'category': 'passive', 'aura': True, 'keywords': ['Аура'], 'effects': [{'stat': 'ac', 'value': 1, 'duration': 'aura'}]}, 'Пример настройки')
        equipment = text.split('## Глава 5.', 1)[1].split('## Глава 6.', 1)[0]
        for line in equipment.splitlines():
            if not line.startswith('|') or '---' in line or 'Название' in line:
                continue
            cells = [s.strip() for s in line.strip('|').split('|')]
            if len(cells) < 5: continue
            name, value, price, kind, special = cells[:5]
            data = {'keywords': [kind]}
            if value.startswith('+'):
                data['armor'] = int(value[1:])
            elif re.fullmatch(r'\d+к\d+', value):
                data.update(dice=value, stat=SCHOOL.get(kind.split(',')[0].strip(), 'str'),
                            keywords=[x.strip() for x in kind.split(',')])
                data['crit'] = 1 if 'Крит 1' in special else 0
            else: continue
            add('item', name, f'{kind}. {special} Стоимость: {price}', data)
        self.stdout.write(f'Справочник: {Entry.objects.count()} записей. Мастер готов.')
