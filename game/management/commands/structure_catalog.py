"""Attach book navigation metadata without overwriting edited rules."""
import re
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from game.models import Clock, Entry


class Command(BaseCommand):
    help = 'Структура умений: расы, классы, школы, остальные разделы книги.'

    @transaction.atomic
    def handle(self, **options):
        clock, _ = Clock.objects.select_for_update().get_or_create(pk=1)
        text = (settings.BASE_DIR / 'rules/player-book.txt').read_text()
        contexts = {}
        chapter, source = 0, ''
        for number, line in enumerate(text.splitlines(), 1):
            match = re.match(r'^## Глава (\d+)\.', line)
            if match:
                chapter, source = int(match[1]), ''
            if line.startswith('### '):
                source = line[4:].strip()
            contexts[number] = (chapter, source)
        # Racial traits are prose in chapter 2, not the framed abilities used elsewhere.
        section = text.split('## Глава 2.', 1)[1].split('## Глава 3.', 1)[0]
        for match in re.finditer(r'^### ([^\n]+)\n(.*?)(?=^### |\Z)', section, re.M | re.S):
            race = match[1].strip()
            base = re.split(r'^#### |^\{\{|^!\[|^\\(?:column|page)', match[2], maxsplit=1, flags=re.M)[0].strip()
            traits = base.split('\n\n', 1)[-1].strip()
            Entry.objects.get_or_create(kind='ability', name=f'Расовые особенности: {race}', defaults={
                'description': traits, 'source': 'Книга игрока, глава 2',
                'data': {'category': 'passive', 'manual': True, 'keywords': ['Расовое'],
                         'source_name': race, 'book_group': 'race',
                         'book_order': text[:text.index('### ' + race + '\n')].count('\n') + 1}})
        changed = 0
        for entry in Entry.objects.filter(kind='ability'):
            data = dict(entry.data)
            line = re.search(r'строка (\d+)', entry.source)
            chapter, source = contexts.get(int(line[1]), (0, '')) if line else (0, '')
            group = ('race' if chapter == 2 else 'class' if chapter == 3 else
                     'school' if chapter == 4 or (chapter == 9 and source.startswith('Школа ')) else
                     'background' if chapter == 8 else 'craft' if chapter == 9 else 'other')
            data.setdefault('book_group', group)
            data.setdefault('book_order', int(line[1]) if line else 999999)
            if source:
                data.setdefault('source_name', source)
            if data != entry.data:
                entry.data = data
                entry.save(update_fields=['data'])
                changed += 1
        clock.revision += 1
        clock.save(update_fields=['revision'])
        self.stdout.write(f'Структура справочника обновлена: {changed} записей.')
