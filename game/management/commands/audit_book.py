from collections import Counter
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from game.models import Entry, Clock
from game.book_audit import records, abilities


class Command(BaseCommand):
    help = 'Дополнить справочники и исправить импорт книги, сохраняя правки мастера.'

    @transaction.atomic
    def handle(self, **options):
        clock, _ = Clock.objects.select_for_update().get_or_create(pk=1)
        text=(settings.BASE_DIR/'rules/player-book.txt').read_text()
        for kind,name,desc,data in records(text):
            entry,created=Entry.objects.filter(personal_character__isnull=True).get_or_create(kind=kind,name=name,defaults={'description':desc or '', 'data':data,'source':'Книга игрока'})
            if not created:
                entry.data={**data,**entry.data}
                entry.save(update_fields=['data'])
        seen=Counter()
        for name,desc,data,source in abilities(text):
            seen[name]+=1
            display=name if seen[name]==1 else name+' · '+data['source_name']
            entry=Entry.objects.filter(personal_character__isnull=True).filter(kind='ability',source=source).first()
            if not entry: entry=Entry.objects.filter(personal_character__isnull=True).filter(kind='ability',name=display).first()
            if not entry: entry=Entry(kind='ability',name=display,source=source)
            if not entry.data.get('reviewed'):
                # Preserve deliberate additions while repairing fields owned by the original importer.
                for key in ['effects','target','automation_notes']:
                    entry.data.pop(key,None)
                entry.data={**entry.data,**data,'book_compiled':2}
                entry.description=desc
                entry.name=display
            else:
                for key in ['school_name','range','book_group','source_group']:
                    entry.data.setdefault(key,data.get(key,''))
            entry.save()
        for name in ['Живучесть','Укрепленные органы']:
            e=Entry.objects.filter(personal_character__isnull=True).filter(kind='ability',name=name).first()
            if e and not e.data.get('reviewed'):
                e.data['passive_hp']=10
                e.save(update_fields=['data'])
        for e in Entry.objects.filter(personal_character__isnull=True).filter(kind='ability',name__in=['Стандартная атака','Провоцированная атака']):
            e.data['system']=True
            for key,value in dict(weapon=True,damage=True,rolls=True,formula='1Ор + Мод').items():
                e.data.setdefault(key,value)
            e.save(update_fields=['data'])
        Entry.objects.filter(personal_character__isnull=True).get_or_create(kind='ability',name='Провоцированная атака',defaults={
            'source':'Книга игрока, глава 7','description':'Реакция: стандартная атака оружием по цели, вызвавшей реакцию. Мастер определяет наличие провокации.',
            'data':{'system':True,'category':'active','action':'reaction','circle':0,'weapon':True,'damage':True,'rolls':True,'formula':'1Ор + Мод','book_group':'other'}})
        # Convert dictionary group headings to actual specialization entries.
        Entry.objects.filter(personal_character__isnull=True).filter(kind='specialization',name__in=['Географические','Профессии','Стихии','Навыки','Местности']).update(archived=True)
        # Import all weapon traits, not just the weapon family.
        import re
        section=text.split('## Глава 5.',1)[1].split('## Глава 6.',1)[0]
        for line in section.splitlines():
            cells=[x.strip() for x in line.strip('|').split('|')]
            if not line.startswith('|') or len(cells)<5: continue
            name,value,price,family,special=cells[:5]
            e=Entry.objects.filter(personal_character__isnull=True).filter(kind='item',name=name).first()
            if not e or e.data.get('reviewed'): continue
            e.data.update(keywords=[x.strip() for x in (family+','+special).split(',') if x.strip()],
                          families=[x.strip() for x in family.split(',')],
                          item_type='armor' if 'доспех' in family.lower() else 'shield' if family=='Щиты' else 'weapon',
                          hit=-1 if '-1 к попаданию' in special else 0,
                          hands=2 if 'Двуручное' in special or 'Друручное' in special else 1,
                          no_proficiency='Не требует владения' in special,
                          price=int(price) if price.isdigit() else 0)
            e.save(update_fields=['data'])
        for word in sorted({k for e in Entry.objects.filter(personal_character__isnull=True).filter(kind='ability') for k in e.data.get('keywords',[]) if len(k)<160}):
            Entry.objects.filter(personal_character__isnull=True).get_or_create(kind='keyword',name=word,defaults={'source':'Книга игрока'})
        clock.revision+=1;clock.save(update_fields=['revision'])
        self.stdout.write('Справочники, формулы, источники и свойства экипировки сверены с книгой.')
