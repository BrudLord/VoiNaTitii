"""Status stacking and explicit, source-selected elemental reactions."""
import re

STATUS = {'Поджог':('status',1),'Влага':('status',1),'Кислота':('ac',-1),'Шок':('status',1),
          'Мороз':('speed',-1),'Яд':('status',1),'Благословение':('hit',1),'Проклятье':('hit',-1),
          'Ослабление':('damage',-1),'Замедление':('speed',-1),'Оглушение':('status',1),
          'Кровотечение':('status',1),'Продолжительный урон':('status',1),'Сон':('status',1),'Страх':('status',1),
          'Обездвижен':('status',1),'Ослепление':('status',1),'Метка':('status',1),'БП':('target_hit',1),'Сбит с ног':('status',1),'Насыщение':('status',1),'Рассеивание':('status',1)}
NEUTRAL=[('Поджог','Влага'),('Поджог','Мороз'),('Кислота','Шок'),('Благословение','Проклятье'),('Мороз','Яд')]
CONSTRUCTIVE=[('Благословение','Поджог','Священное пламя'),('Благословение','Яд','Вирус'),('Благословение','Мороз','Чистые льды'),
 ('Благословение','Влага','Очищение'),('Влага','Кислота','Взрыв'),('Влага','Шок','Оцепенение'),('Влага','Мороз','Заморозка'),
 ('Проклятье','Поджог','Некропламя'),('Проклятье','Кислота','Размякшая плоть'),('Проклятье','Шок','Проклятый разряд'),
 ('Проклятье','Мороз','Ледяная тьма'),('Мороз','Шок','Сверхпроводник'),('Поджог','Яд','Гипертермия')]
ELEMENTAL = list(STATUS)[:8]+[r for _,_,r in CONSTRUCTIVE]
STUN = ['Оглушение','Оцепенение','Заморозка']


def status_name(effect):
    if effect.get('status'): return effect['status']
    name=re.sub(r'\s+[+-]?\d+$','',effect.get('name',''))
    return name if name in STATUS and effect.get('stat',STATUS[name][0])==STATUS[name][0] else ''


def reaction_options(target, incoming):
    name=status_name(incoming)
    options=[]
    for old in target.runtime.get('effects',[]):
        other=status_name(old)
        if not other or name==other: continue
        result=next(('Нейтрализация' for a,b in NEUTRAL if {a,b}=={name,other}),None)
        result=result or next((r for a,b,r in CONSTRUCTIVE if {a,b}=={name,other}),None)
        if name=='Насыщение' and other in ELEMENTAL: result='Насыщение'
        if name=='Рассеивание' and other in ['Поджог','Влага','Кислота','Яд','Мороз']:result='Рассеивание'
        if result: options.append({'key':old['key'],'name':result,'effect':old})
    return options


def apply_status(target, incoming, choice=None, *, change=None, roll=None, spread=None):
    from .rules import put_effect
    name=status_name(incoming)
    options=reaction_options(target,incoming)
    if options:
        selected=next((o for o in options if o['key']==choice),None)
        if not selected: raise ValueError('Выберите стихийную реакцию для '+target.name)
        old=selected['effect'];result=selected['name']
        if result=='Рассеивание':
            from .dispersion import apply
            apply(change,target,incoming,old,spread)
            return
        strength=abs(old['value'])+abs(incoming['value'])
        if result in ['Взрыв','Проклятый разряд','Ледяная тьма']:
            damage=strength
            if result=='Проклятый разряд':
                if isinstance(roll,bool) or not re.fullmatch(r'\d+',str(roll) if roll is not None else '') or not strength<=int(roll)<=strength*6:
                    raise ValueError(f'Введите итог физического броска {strength}к6 для Проклятого разряда ({strength}–{strength*6})')
                damage=int(roll)
            if change is None:raise ValueError('Мгновенная реакция должна быть записана в журнал действия')
            change.inputs.setdefault('instant_reactions',[]).append({'name':result,'target':target.name,'target_id':target.pk,
                'strength':strength,'damage':damage,'damage_type':'Физический' if result=='Взрыв' else '', 'area':2 if result=='Взрыв' else 0,
                'ignore_resistance':result=='Проклятый разряд','roll':damage if result=='Проклятый разряд' else None,
                'source':incoming.get('source',''),'source_id':incoming.get('source_id'),
                'temp_hp':strength*2 if result=='Ледяная тьма' else 0})
            target.runtime['effects'].remove(old)
            return
        target.runtime['effects'].remove(old)
        if result=='Нейтрализация': return
        if result=='Насыщение':
            old['value']=-strength if old['value']<0 else strength
            if old.get('duration','turns')=='turns':
                old['remaining']=max(old.get('max_turns',3),old.get('remaining',0))
            if other_note:=old.get('note'):
                if other_note.startswith(('В начале хода','За каждое совершённое действие')):
                    old['note']='Сила эффекта увеличена Насыщением. Изменение ХП вносит мастер.'
            put_effect(target,old);return
        # HP changes from reaction strength remain manual, as agreed with the user.
        incoming.update(name=result,status=result,key='status:'+result,stat='status',value=strength,
                        note='Последствия реакции по книге; изменение ХП вносит мастер.')
        if result=='Гипертермия':incoming['note']=f'За каждое совершённое действие: {strength} урона. ХП вносит мастер.'
        if result=='Некропламя':incoming['note']=f'В начале хода: {strength*2} продолжительного урона. ХП вносит мастер.'
        if result in ['Священное пламя','Вирус']:incoming['note']=f'В начале хода цели: {strength} урона Вокруг 1. ХП вносит мастер.'
        if result=='Размякшая плоть': incoming.update(stat='damage',value=-strength)
    elif name in ['Насыщение','Рассеивание']:
        return
    elif name:
        incoming['key']='status:'+name
        incoming['status']=name
        if name=='Шок':incoming['note']=f'Предоставляет БП {incoming["value"]}; не может окружать.'
    if status_name(incoming) in STUN:
        old=next((e for e in target.runtime.get('effects',[]) if status_name(e)==status_name(incoming)),None)
        if old:
            incoming['value']+=old['value'];target.runtime['effects'].remove(old)
        incoming['duration']='actions'
        incoming.pop('remaining',None)
    put_effect(target,incoming)


def skip_stunned_action(character):
    """Consume one required skipped action; remaining strength survives turn boundaries."""
    if not character.runtime.get('stun_pending',0):return False
    for effect in list(character.runtime.get('effects',[])):
        if status_name(effect) in STUN and effect.get('value',0)>0:
            effect['value']-=1
            if not effect['value']:character.runtime['effects'].remove(effect)
            character.runtime['stun_pending']-=1
            return True
    character.runtime['stun_pending']=0
    return False
