import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from game.coverage import inventory


class Command(BaseCommand):
    help='Сопоставить все блоки книги с кандидатами обработчиков, без автоматической отметки готовности.'

    def add_arguments(self,parser):
        parser.add_argument('--output',default='docs/book-coverage.json')

    def handle(self,**options):
        result=inventory((settings.BASE_DIR/'rules/player-book.txt').read_text())
        path=Path(options['output']);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        self.stdout.write(json.dumps(result['summary'],ensure_ascii=False))
