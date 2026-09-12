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
        data={'subrace_traits':subrace_traits,'chosen_stat_bonus':1 if name=='Человек' else 0,'hp_bonus':5 if name=='Гном' else 0,'ac_bonus':1 if name=='Людоящер' else 0,
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
        formula_text=description.replace('\\*','*')
        expressions=re.findall(r'(?:\d+\s*(?:к\d+|Ор)(?:\s*[+−-]\s*(?:\d+\s*\*?\s*)?Мод)?|(?:\d+\s*\*\s*)?Мод)\s*(?=(?:[А-Яа-яЁё]+\s+){0,3}урона)',formula_text)
        if not expressions:
            expressions=re.findall(r'(?:получает|получают)\s+(\d+\s*(?:к\d+|Ор)(?:\s*[+−-]\s*(?:\d+\s*\*?\s*)?Мод)?|Мод)\s+(?:Физического|Физическим|Огнём|Огнем|Водой|Землёй|Землей|Воздухом|Тьмой|Светом|Молнией|Холодом|Природой|Изначального)\b',formula_text)
        if not expressions:
            expressions=re.findall(r'\b[Уу]рон\s+(\d+\s*(?:к\d+|Ор)(?:\s*[+−-]\s*(?:\d+\s*\*?\s*)?Мод)?)',description)
        if expressions:
            data.update(formula=expressions[0].replace(' ','').replace('−','-'),damage=True,
                        weapon='Ор' in expressions[0],formula_variants=list(dict.fromkeys(expressions)))
        healing=re.search(r'(\d+к\d+(?:\s*\+\s*\d*\\?\*?\s*Мод)?)\s*(?:ХП|хитов)',description)
        if healing and not expressions: data['formula']=healing[1].replace('\\','')
        fixed_damage=re.search(r'Цель получает (\d+) урона',description)
        if fixed_damage and not expressions: data.update(formula=fixed_damage[1],damage=True)
        own_hit=re.search(r'(?:^|\.\s+)Вы получаете ([+−-]\d+) к попаданию для этой атаки\.',description)
        data['attack_hit_bonus']=int(own_hit[1].replace('−','-')) if own_hit and not re.search(r'если|когда',description,re.I) else 0
        data['damage_from_bp']=bool(re.search(r'(?:^|\.\s+)Урон увеличивается на размер БП\.',description))
        if re.search(r'при промахе (?:(?:цель|цели) получа(?:ет|ют) )?половину(?: урона)?',description,re.I):data['miss_damage_divisor']=2
        data['automatic_hit']=bool(re.match(r'Цел[ьи] автоматически получа(?:ет|ют)\b',description))
        data['rolls']=category=='active' and ('урона' in description or bool(healing)) or category=='active' and (bool(expressions) or bool(re.search(r'\d+к\d+|брос[а-я]*|провер[а-я]*',description,re.I)))
        if data['automatic_hit']:
            data['rolls']=bool(re.search(r'\d+к\d+|брос[а-я]*|провер[а-я]*',description,re.I)) or bool(data.get('weapon'))
        if data.get('weapon') and school: data['requires']=[school]
        # Only literal, unconditional single-target clauses are compiled automatically.
        simple_description=description.replace(own_hit[0],'.') if own_hit and data['attack_hit_bonus'] else description
        simple=not re.search(r'если|когда|вместо|случайн|кажд|выбер|выбор|можете|следующ|при |попадани|промах| или |аура|стойка',simple_description+' '+keys,re.I)
        from .book_effects import literal_effects
        effects,target=literal_effects(description) if simple and category=='active' else ([],None)
        if data.get('miss_damage_divisor') and category=='active':
            effects,target=literal_effects(description.split('.')[0])
            data['target']='multiple' if description.startswith('Цели ') else 'single'
            sentences=[s.strip() for s in description.split('.') if s.strip()]
            if len(sentences)==2 and not re.search(r'если|когда|вместо|может| или ',sentences[0],re.I) and re.match(r'^Цел[ьи] ',sentences[0]) and re.fullmatch(r'При промахе цел[ьи] получа(?:ет|ют) половину урона(?: и не получает эффект)?',sentences[1],re.I):
                data['manual']=False
        if effects: data.update(effects=effects,target=target,automation_notes='Числовые эффекты применяются автоматически; остальное — по описанию.')
        if any(k.startswith('Аура') for k in keywords):
            data.update(aura=True,category='passive',target='multiple',rolls=False)
            # Track the owner's chosen recipients even when the special trigger is manual.
            data['effects']=[{'stat':'status','value':0,'name':clean(m[1]),'duration':'aura'}]
            direct=re.match(r'(?:Вы и союзники|Союзники|Противники|Цели) в ауре получа(?:ют|ете) ([+-]\d+) к (урону|попаданию)\.',description)
            if direct:
                data['effects']=[{'stat':'damage' if direct[2]=='урону' else 'hit','value':int(direct[1]),'name':clean(m[1]),'duration':'aura'}]
                data['automation_notes']='Базовый бонус действует на выбранных получателей; усиление и особые условия — по описанию.'
            else:
                data['automation_notes']='Выбранные получатели видят ауру в листе. Особые последствия и срабатывания — по описанию.'

        if clean(m[1])=='Парирующие потоки':
            data.update(damage_reduction={'divisor':2,'unarmed':True},manual=False)
        if clean(m[1])=='Бой без оружия':
            data.update(unarmed_combat={'dice':'1к8','ignore_requirements':True},manual=False)
        if clean(m[1])=='Элементальная сфера':
            data.update(elemental_sphere={'strength':1},manual=False,target='single')
        if clean(m[1])=='Широкий замах':
            data['wide_swing']={'hit':1,'reach':1}
        if clean(m[1])=='Скорострельность':
            data.update(rapid_fire=True,manual=False)
        from .attack_sequences import BOOK as SEQUENCES
        if clean(m[1]) in SEQUENCES:
            data['attack_sequence']=dict(SEQUENCES[clean(m[1])])
            if clean(m[1]) not in ['Захват пространства','Тормозящие стрелы']:
                data['manual']=False
        yield clean(m[1]),description,data,f'Книга, строка {before.count(chr(10))+1}'
