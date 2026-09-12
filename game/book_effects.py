"""Literal recipient clauses only; conditional and alternative effects stay separate."""
import re
from .statuses import STATUS, STUN

RECIPIENT = re.compile(r'(?:^|(?<=[.!?])\s+)(Цель|Цели(?:\s+[^.!?]*?)?|Противники(?:\s+[^.!?]*?)?|Союзник)\s+(?:автоматически\s+)?(?:получает|получают|восстанавливает|восстанавливают)\s+([^.!?]+)', re.I)


def duration(tail):
    if re.match(r'\s+до конца хода\b',tail,re.I):return {'duration':'current_turn'}
    if re.match(r'\s+(?:до конца (?:своего|следующего)|на время)',tail,re.I):return None
    battle = re.match(r'\s+до конца боя\b', tail, re.I)
    if battle:return {'duration':'battle'}
    match = re.match(r'\s+на\s+(\d+|один|одного|два|двух|три|трех|трёх)\s+ход', tail, re.I)
    words={'один':1,'одного':1,'два':2,'двух':2,'три':3,'трех':3,'трёх':3}
    return {'turns':words.get(match[1].lower(),int(match[1]) if match[1].isdigit() else 3)} if match else {'turns':3}


def literal_effects(description):
    effects=[];multiple=False;recipient=None
    for clause in RECIPIENT.finditer(description):
        subject,body=clause.groups()
        identity=subject.lower()
        if recipient is not None and identity!=recipient:continue
        recipient=identity
        # A subsequent actor, a zone or trigger is not the same recipient clause.
        body=re.split(r'\b(?:Ваши|Вы|Союзники|Противники|Цели)\b',body)[0]
        clause_effects=[]
        for match in re.finditer(r'(?:^|,\s*|\bи\s+)(\d+)\s+(Временных (?:хитов|ХП)|временных ХП|ХП)',body,re.I):
            temporary=match[2].lower().startswith('временных')
            if temporary or 'восстанавлив' in clause[0].lower():
                clause_effects.append({'stat':'temp' if temporary else 'hp','value':int(match[1])})
        bonuses={'урону':'damage','попаданию':'hit','КД':'ac','скорости':'speed'}
        for match in re.finditer(r'(?:^|,\s*|\bи\s+)([+−-]\d+) (?:к )?(урону|попаданию|КД|скорости)\b',body):
            timing=duration(body[match.end():])
            if timing is not None:
                clause_effects.append({'stat':bonuses[match[2]],'value':int(match[1].replace('−','-')),
                                       'name':'Бонус к '+match[2],**timing})
        for status,(stat,sign) in STATUS.items():
            if status in ['Сон','Страх']:continue
            pattern=r'(?<![\w])'+('Метк[ау]' if status=='Метка' else re.escape(status))+r'(?:\s+(\d+))?(?![\w])'
            for match in re.finditer(pattern,body):
                if not match[1] and status not in ['Сон','Страх','Обездвижен','Ослепление','Метка','Сбит с ног']:continue
                tail=body[match.end():]
                if status=='Метка' and re.match(r'\s+[А-ЯЁ]',tail):continue
                if re.match(r'[\s\\]*[*×+−-]',tail):continue
                timing=duration(tail)
                if timing is None:continue
                effect={'stat':stat,'value':sign*int(match[1] or 1),'name':status,'key':'status:'+status,**timing}
                if status=='Сбит с ног' and timing=={'turns':3} and not tail.lstrip().startswith('на '):
                    effect.pop('turns',None);effect['duration']='battle'
                if status in STUN:effect.pop('turns',None);effect['duration']='actions'
                clause_effects.append(effect)
        if clause_effects:
            multiple=multiple or subject.lower().startswith(('цели','противники'))
            effects.extend(clause_effects)
    return effects,'multiple' if multiple else 'single'
