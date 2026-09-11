"""Structured book import, with conservative automation and stable source identities."""
import re
from .book_choices import SCHOOL_NAMES

STAT_NAMES = {'Силе':'str','Ловкости':'dex','Телосложению':'con','Интеллекту':'int','Мудрости':'wis','Харизме':'cha'}
SKILLS = {'Атлетика':'str','Акробатика':'dex','Воровство':'dex','Магия':'int','История':'int','Целительство':'int',
          'Знание улиц':'wis','Восприятие':'wis','Выживание':'wis','Убеждение':'cha'}
SCHOOL_STATS = dict(zip(SCHOOL_NAMES.values(), ['int','int','wis','wis','int','cha','cha','int','wis','cha','con','dex','dex','str','str','con','dex','str','dex','str','con']))


def clean(text):
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)[^\n]*', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<[^>]+>|\\(?:page|column)|\{\{[^\n]*|\}\}', '', text)
    return text.replace('**','').strip()


def chapters(text, chapter):
    section = text.split(f'## Глава {chapter}.', 1)[1].split('## Глава ',1)[0]
    return [(m[1].strip(),m[2]) for m in re.finditer(r'^### ([^\n]+)\n(.*?)(?=^### |\Z)',section,re.M|re.S)]


def records(text):
    for name, body in chapters(text,2):
        subrace_traits = {}
        for m in re.finditer(r'^#### ([^\n]+)\n(.*?)(?=^#### |\Z)',body,re.M|re.S):
            bonus = re.search(r'получают \+1 к \*\*([^*]+)', m[2])
            if bonus: subrace_traits[m[1].strip()] = {'stat': STAT_NAMES.get(bonus[1]), 'value':1}
        data={'subrace_traits':subrace_traits,'hp_bonus':5 if name=='Гном' else 0,'ac_bonus':1 if name=='Людоящер' else 0,
              'element_damage':1 if name=='Эльф' else 0,'step':2 if name=='Туват' else 1,'resistance':1 if name=='Отродье' else 0}
        yield 'race',name,None,data
    for name, body in chapters(text,3):
        skill = re.search(r'\*\*Навык:\*\*\s*([^\n]+)',body)
        armor = re.search(r'\*\*Владения:\*\*\s*([^\n]+)',body)
        equipment = re.search(r'##### Снаряжение\s*(.*?)(?=#####|\Z)',body,re.S)
        yield 'class',name,None,{'skill':clean(skill[1]) if skill else '', 'proficiencies':clean(armor[1]) if armor else '',
                                'starting_equipment':clean(equipment[1]) if equipment else '',
                                'extra_schools':3 if name=='Стихийный маг' else 1}
    for name, body in chapters(text,8):
        if name in ['Мировоззрение','Приоритеты']: continue
        skill = re.search(r'\*\*Навык\*\*:\s*([^\n]+)',body)
        spec = re.search(r'\*\*Специализация\*\*:\s*([^\n]+)',body)
        equipment = re.search(r'\*\*Бонусное снаряжение\*\*:\s*([^\n]+)',body)
        yield 'background',name,None,{'skill':clean(skill[1]) if skill else '', 'specialization':clean(spec[1]) if spec else '',
                                     'starting_equipment':clean(equipment[1]) if equipment else ''}
    for group, body in chapters(text,8):
        if group == 'Приоритеты':
            for m in re.finditer(r'^#### ([^\n]+)\n(.*?)(?=^#### |\Z)',body,re.M|re.S):
                yield 'effect',m[1].strip(),clean(m[2]),{'priority':True}
    for group, body in chapters(text,10):
        for name in re.findall(r'^- (.+)',body,re.M):
            yield 'specialization',name.strip(),'Подходящая специализация даёт +3 к проверке.',{'group':group}
    for name, body in chapters(text,9):
        if not name.startswith('Школа '):
            yield 'craft',name,clean(body),{}
    for m in re.finditer(r'\{\{(?:descriptive|note)\s*\n##### ([^\n]+)\n(.*?)\n\}\}',text,re.S):
        if m.start()>text.index('## Глава 6.'):
            yield 'effect',clean(m[1]),clean(m[2]),{}


def abilities(text):
    for m in re.finditer(r'\{\{monster,frame\s*\n##### ([^\n]+)\n(.*?)\n\}\}',text,re.S):
        before=text[:m.start()];chapter=int(re.findall(r'^## Глава (\d+)\.',before,re.M)[-1])
        headers=list(re.finditer(r'^### ([^\n]+)',before,re.M));source=headers[-1][1].strip()
        recent=before[headers[-1].start():]
        subheaders=re.findall(r'^#### ([^\n]+)',recent,re.M)
        subgroup=subheaders[-1].strip() if subheaders else ''
        parts=m[2].strip().split('___')
        # A single separator means no keyword line, not a missing description.
        keys=clean(parts[1]) if len(parts)>2 else ''
        description=clean('___'.join(parts[2:]) if len(parts)>2 else parts[-1])
        circle=re.findall(r'^##### ([123]) круг',recent,re.M)
        noncombat=chapter in [8,9] or (chapter==3 and '#### Классовые значения' not in recent)
        category='noncombat' if noncombat else 'passive' if 'Пассив' in keys else 'active'
        keywords=[x.strip() for x in re.split(r',|\n',keys) if x.strip()]
        group='race' if chapter==2 else 'class' if chapter==3 else 'school' if source.startswith('Школа ') else 'background' if chapter==8 else 'craft' if chapter==9 else 'other'
        school=SCHOOL_NAMES.get(source.removeprefix('Школа ')) if source.startswith('Школа ') else None
        data={'category':category,'circle':int(circle[-1]) if circle else 0,'keywords':keywords,
              'source_name':source,'source_group':subgroup,'book_group':group,'book_order':before.count('\n')+1,
              'action':next((v for k,v in [('Малым','minor'),('Свободным','free'),('Реакция','reaction'),('Движение','move')] if k in keys),'main'),
              'manual':True,'reliable':any('Надёжн' in k or 'Надежн' in k for k in keywords)}
        if school:
            data.update(stat=SCHOOL_STATS[school],school_name=school)
            data['keywords'].append(school)
        ranges=[k for k in keywords if re.search(r'Ближний|Дальнобойный|Вокруг|Линия|Сфера|Конус',k)]
        data['range']=' · '.join(ranges)
        expressions=re.findall(r'(?:\d+\s*(?:к\d+|Ор)(?:\s*[+−-]\s*(?:\d+\s*\*?\s*)?Мод)?|(?:\d+\s*\*\s*)?Мод)\s*(?=урона)',description)
        if expressions:
            data.update(formula=expressions[0].replace(' ','').replace('−','-'),damage=True,
                        weapon='Ор' in expressions[0],formula_variants=list(dict.fromkeys(expressions)))
        healing=re.search(r'(\d+к\d+(?:\s*\+\s*\d*\\?\*?\s*Мод)?)\s*(?:ХП|хитов)',description)
        if healing and not expressions: data['formula']=healing[1].replace('\\','')
        fixed_damage=re.search(r'Цель получает (\d+) урона',description)
        if fixed_damage and not expressions: data.update(formula=fixed_damage[1],damage=True)
        data['rolls']=category=='active' and ('урона' in description or bool(healing)) or category=='active' and (bool(expressions) or bool(re.search(r'\d+к\d+|брос[а-я]*|провер[а-я]*',description,re.I)))
        if data.get('weapon') and school: data['requires']=[school]
        # Only literal, unconditional single-target clauses are compiled automatically.
        simple=not re.search(r'если|когда|вместо|случайн|кажд|выбер|выбор|можете|следующ|при |попадани|промах| или |аура|стойка',description+' '+keys,re.I)
        effects=[]
        if simple and category=='active':
            for pattern,stat in [(r'Цель (?:получает|восстанавливает) (\d+) (?:Временных (?:хитов|ХП)|временных ХП)', 'temp'),
                                 (r'Цель восстанавливает (\d+) ХП','hp')]:
                for match in re.finditer(pattern,description): effects.append({'stat':stat,'value':int(match[1])})
            for status,stat,sign in [('Благословение','hit',1),('Проклятье','hit',-1),('Кислота','ac',-1),('Мороз','speed',-1),('Ослабление','damage',-1),('Поджог','status',1),('Влага','status',1),('Яд','status',1),('Шок','status',1),('Оглушение','status',1),('Замедление','speed',-1)]:
                match=re.search(r'(?:эффект |получает |и )'+status+r' (\d+)',description)
                if match: effects.append({'stat':stat,'value':sign*int(match[1]),'name':status,'key':'status:'+status,'turns':3})
        if effects: data.update(effects=effects,target='single',automation_notes='Числовые эффекты применяются автоматически; остальное — по описанию.')
        yield clean(m[1]),description,data,f'Книга, строка {before.count(chr(10))+1}'
