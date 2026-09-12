"""Inventory source rules and candidate handlers without claiming mechanical coverage."""
import hashlib
import re
from collections import Counter
from .book_audit import abilities, clean
from .enchantments import BOOK
from .weaponry import UPGRADES
from .roll_pools import PROFILES
from .crafting import ALCHEMY

FEATURES={
 'dice':r'\d+\s*к\d+|брос[а-яё]*|провер[а-яё]*',
 'modifier':r'\bМод\b',
 'conditional':r'если|когда|при попадании|при промахе|при провале',
 'once_per_turn':r'(?:один|одного|1) раз[а]? за ход|раза за ход|раз за ход|раз в ход',
 'once_per_battle':r'первый раз за бой|раз за бой|раз в бою',
 'duration':r'до конца|следующ[а-яё]* ход|\d+ ход|\d+ раунд',
 'targets':r'цел[ьи]|союзник|получател',
 'distribution':r'распредел',
 'choice':r'выбер|выбор|выбира|режим|случайн',
 'aura':r'аура|в ауре',
 'stance':r'стойк',
 'reaction':r'реакци[яиейю]',
 'enhancement':r'усиление|усилени',
 'summon':r'призыва|призыв|призван',
 'mount':r'всадник|скакун|наездник|верхом',
 'craft':r'изготов|приготов|зачарован|варке|ингредиент|ингридиент',
 'healing':r'восстан[а-яё]*.*(?:ХП|хит)|лечени|исцелен',
 'temporary_hp':r'временн[а-яё]* (?:ХП|хит)',
}
FRAME=re.compile(r'\{\{(monster,frame|note|descriptive)\s*\n##### ([^\n]+)\n(.*?)\n\}\}',re.S)
HEADING=re.compile(r'^(#{2,5}) ([^\n]+)',re.M)


def inventory(text):
    compiled={int(source.rsplit(' ',1)[1]):data for _,_,data,source in abilities(text)}
    frames=list(FRAME.finditer(text));headers=list(HEADING.finditer(text));result=[]
    chapters=[m for m in headers if m[1]=='##' and m[2].startswith('Глава ')]
    def add(kind,title,start,end,body,data=None):
        line=text.count('\n',0,start)+1
        chapter=next((m[2].strip() for m in reversed(chapters) if m.start()<=start),'Введение')
        handlers=[]
        if data:
            if data.get('category')=='active':handlers.append('game.views.use_ability: actions/charges')
            if data.get('formula'):handlers.append('game.rules.formula: parsed expression')
            if data.get('effects'):handlers.append('game.views.use_ability: compiled numeric effects')
        if title in BOOK:handlers.append('game.enchantments: '+title)
        if title in UPGRADES:handlers.append('game.weaponry: '+title)
        if title in PROFILES:handlers.append('game.roll_pools: '+title)
        if title in ALCHEMY:handlers.append('game.crafting: production')
        if title=='Масло точности':handlers.append('game.alchemy.apply_oil')
        if title=='Глыба':handlers.append('game.passives.boulder_bonus')
        if title=='Интуитивное владение':handlers.append('game.rules.computed: bow proficiency')
        if title=='Мистическая точность':handlers.append('game.views.serialize_char: standard attack hit')
        if title in ['Мистические стрелы','Двойной заряд']:handlers.append('game.mystic_arrows')
        if title=='Оглушение Х':handlers.extend(['game.statuses.skip_stunned_action','game.views.execute: scene.turn'])
        if title=='Молниеносные рефлексы':handlers.extend(['game.passives.reflex_reason','game.rules.computed: reactions'])
        if title=='Отложить действие':handlers.append('game.readied')
        result.append({'id':f'book:{line}','kind':kind,'title':title,'chapter':chapter,
                       'source':{'path':'rules/player-book.txt','line':line,'end_line':text.count('\n',0,end)+1,
                                 'sha256':hashlib.sha256(text[start:end].encode()).hexdigest()},
                       'features':[name for name,pattern in FEATURES.items() if re.search(pattern,body,re.I|re.S)],
                       'compiled_fields':sorted(data.keys()) if data else [],'candidate_handlers':handlers,
                       'verification':'needs_scenario_review'})
    for m in frames:
        line=text.count('\n',0,m.start())+1
        add('ability' if m[1]=='monster,frame' else m[1],clean(m[2]),m.start(),m.end(),clean(m[3]),compiled.get(line))
    outside=[h for h in headers if not any(m.start()<=h.start()<m.end() for m in frames)]
    for index,h in enumerate(outside):
        end=outside[index+1].start() if index+1<len(outside) else len(text)
        body=FRAME.sub('',text[h.end():end])
        if clean(body):add('section',clean(h[2]),h.start(),end,clean(body))
    result.sort(key=lambda row:row['source']['line'])
    counts=Counter(row['kind'] for row in result)
    return {'schema':1,'scope':'Player book source inventory; candidate handlers are not proof of complete behavior.',
            'source_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'summary':{'units':len(result),'by_kind':dict(counts),
                       'by_feature':dict(Counter(feature for row in result for feature in row['features'])),
                       'verified':0},'units':result}
