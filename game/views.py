import copy
import difflib
import io
import json
import uuid

from PIL import Image, ImageOps
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import JsonResponse, FileResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .models import Character, Campaign, Squad, Membership, Entry, Item, Session, Scene, Event, Clock, Receipt
from .rules import STATS, ACTIONS, computed, fresh, definition, limit, formula, current_scene, availability, put_effect, Change, undo, rolls_required


def master(user):
    return user.is_authenticated and user.is_superuser and user.username == 'admin'


def require_master(user):
    if not master(user):
        raise PermissionDenied('Доступно только мастеру')


def owned(user, pk):
    char = get_object_or_404(Character, pk=pk)
    if char.owner_id != user.id and not master(user):
        raise PermissionDenied('Можно изменять только своего персонажа')
    return char


def access_campaign(user, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    if not master(user) and not campaign.players.filter(pk=user.pk).exists() and not campaign.memberships.filter(character__owner=user).exists():
        raise PermissionDenied('Вступите в кампанию')
    return campaign


def access_scene(user, pk):
    scene = get_object_or_404(Scene, pk=pk)
    access_campaign(user, scene.session.campaign_id)
    return scene


def bounded(value, low, high):
    number = int(value)
    if not low <= number <= high:
        raise ValueError(f'Число должно быть от {low} до {high}')
    return number


def sign_in(request):
    if request.user.is_authenticated:
        return redirect('/')
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        return redirect('/')
    return render(request, 'auth.html', {'form': form})


def register(request):
    form = UserCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if form.cleaned_data['username'].lower() == 'admin':
            form.add_error('username', 'Этот логин зарезервирован для мастера.')
        else:
            user = form.save()
            login(request, user)
            return redirect('/')
    return render(request, 'auth.html', {'form': form, 'register': True})


@login_required
@ensure_csrf_cookie
def home(request):
    return render(request, 'app.html', {'is_master': master(request.user)})


def serialize_char(c, user):
    scene = current_scene(c)
    abilities = []
    for a in c.abilities.all():
        d = a.data
        hit_bonus = computed(c)['hit'] + sum(int(e.get('value', 0)) for e in c.runtime.get('effects', [])
                    if e.get('keyword') and e['keyword'] in d.get('keywords', []) and e.get('stat') == 'hit')
        abilities.append({'id': a.id, 'name': a.name, 'description': a.description, 'data': d,
                          'hit_bonus': hit_bonus,
                          'remaining': None if limit(c.level, int(d.get('circle', 0))) is None else
                          max(0, limit(c.level, int(d.get('circle', 0))) - c.runtime.get('used', {}).get(str(a.id), 0)),
                          'reason': availability(c, a, scene), 'formula': formula(c, a), 'critical': formula(c, a, True),
                          'rolls_required': rolls_required(a) or bool(a.data.get('weapon'))})
    return {'id': c.id, 'name': c.name, 'owner_id': c.owner_id, 'owner': c.owner.username,
            'editable': c.owner_id == user.id or master(user), 'level': c.level, 'info': c.info,
            'stats': c.stats, 'calc': computed(c), 'runtime': c.runtime, 'abilities': abilities,
            'private_notes': c.private_notes if c.owner_id == user.id else None,
            'revision': c.revision, 'photo': f'/portrait/{c.id}/' if c.photo else '',
            'memberships': list(c.memberships.values('campaign_id', 'squad_id')),
            'items': list(c.items.values('id', 'name', 'quantity', 'equipped', 'slot', 'data')),
            'scene_id': scene.id if scene else None}


@login_required
def state(request):
    clock, _ = Clock.objects.get_or_create(pk=1)
    if request.GET.get('revision') == str(clock.revision):
        return JsonResponse({'unchanged': True, 'revision': clock.revision})
    campaigns = []
    accessible = set()
    for c in Campaign.objects.all():
        member = master(request.user) or c.players.filter(pk=request.user.pk).exists() or c.memberships.filter(character__owner=request.user).exists()
        if member:
            accessible.add(c.id)
        campaigns.append({'id': c.id, 'name': c.name, 'description': c.description, 'member': member,
                          'players': list(c.players.values('id', 'username')) if member else [],
                          'notes': c.notes if member else None, 'note_revision': c.note_revision if member else None,
                          'squads': list(c.squads.values('id', 'name')),
                          'items': list(c.items.values('id', 'name', 'quantity', 'data')) if member else []})
    sessions = [{'id': s.id, 'name': s.name, 'campaign_id': s.campaign_id, 'squad_id': s.squad_id,
                 'characters': list(s.characters.values_list('id', flat=True))}
                for s in Session.objects.filter(campaign_id__in=accessible)]
    scenes = [{'id': s.id, 'session_id': s.session_id, 'name': s.session.name,
               'campaign_id': s.session.campaign_id, 'state': s.state}
              for s in Scene.objects.select_related('session').filter(session__campaign_id__in=accessible)]
    events = Event.objects.select_related('actor').order_by('-id')[:100]
    visible_events = [{'id': e.id, 'actor': e.actor.username, 'label': e.label, 'undone': e.undone,
                       'time': e.created.isoformat(), 'scene_id': e.scene_id, 'inputs': e.inputs}
                      for e in events if e.actor_id == request.user.id or master(request.user) or
                      (e.scene_id and e.scene.session.campaign_id in accessible)]
    return JsonResponse({'revision': clock.revision, 'user': {'id': request.user.id, 'name': request.user.username,
                        'master': master(request.user)}, 'users': list(User.objects.values('id', 'username')) if master(request.user) else [],
                        'characters': [serialize_char(c, request.user)
                        for c in Character.objects.select_related('owner').prefetch_related('abilities', 'items', 'memberships')],
                        'campaigns': campaigns, 'sessions': sessions, 'scenes': scenes, 'events': visible_events,
                        'catalog': list(Entry.objects.filter(archived=False).values('id', 'kind', 'name', 'description', 'data', 'source'))})


def merge_notes(base, ours, theirs):
    """Merge non-overlapping character edits; overlapping edits are explicitly rejected."""
    def edits(a, b):
        return [(i, j, b[x:y]) for tag, i, j, x, y in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if tag != 'equal']
    left, right = edits(base, ours), edits(base, theirs)
    combined = list(right)
    for a in left:
        if a in right:
            continue
        for b in right:
            if max(a[0], b[0]) < min(a[1], b[1]) or a[0] == b[0] or (a[0] <= b[0] < a[1]) or (b[0] <= a[0] < b[1]):
                raise ValueError('Этот фрагмент одновременно изменён другим участником. Ваш текст сохранён в редакторе; сравните с новой версией.')
        combined.append(a)
    result = base
    for i, j, text in sorted(combined, reverse=True):
        result = result[:i] + text + result[j:]
    return result


def execute(user, p):
    op = p.get('op')
    if op == 'character.save':
        c = owned(user, p['id']) if p.get('id') else Character(owner=user, runtime=fresh())
        if not c.pk and p.get('owner'):
            require_master(user)
            c.owner = get_object_or_404(User, pk=p['owner'])
        if c.pk and int(p.get('revision', -1)) != c.revision:
            raise ValueError('Лист изменился. Обновите форму перед сохранением.')
        c.name = str(p.get('name', '')).strip()[:120]
        if not c.name:
            raise ValueError('Укажите имя персонажа')
        c.level = bounded(p.get('level', 1), 1, 100)
        c.stats = {k: bounded(p.get('stats', {}).get(k, 10), -1000, 1000) for k, _ in STATS}
        allowed = ['race_id', 'class_id', 'school_id', 'secondary_school_id', 'subrace', 'craft',
                   'background', 'alignment', 'specializations', 'skills']
        previous_info = dict(c.info)
        c.info = {k: p.get('info', {}).get(k, '') for k in allowed}
        if any(not isinstance(v, (str, int, list)) for v in c.info.values()):
            raise ValueError('Некорректные сведения персонажа')
        for k, kind in [('race_id', 'race'), ('class_id', 'class'), ('school_id', 'school'), ('secondary_school_id', 'school')]:
            if c.info.get(k) and not Entry.objects.filter(pk=c.info[k], kind=kind).exists():
                raise ValueError('Выберите запись из справочника')
        # Keep old sheets editable, but validate new/changed dependent choices.
        def choices_changed(keys):
            return not c.pk or any(str(c.info.get(k) or '') != str(previous_info.get(k) or '') for k in keys)
        if choices_changed(['race_id', 'subrace']) and c.info.get('subrace'):
            race = Entry.objects.filter(pk=c.info.get('race_id'), kind='race').first() if c.info.get('race_id') else None
            if not race or c.info['subrace'] not in race.data.get('subraces', []):
                raise ValueError('Выберите подрасу выбранной расы')
        if choices_changed(['class_id', 'school_id', 'secondary_school_id']):
            school_ids = [c.info[k] for k in ['school_id', 'secondary_school_id'] if c.info.get(k)]
            if len(school_ids) == 2 and str(school_ids[0]) == str(school_ids[1]):
                raise ValueError('Основная и дополнительная школы должны различаться')
            klass = Entry.objects.filter(pk=c.info.get('class_id'), kind='class').first() if c.info.get('class_id') else None
            for school in Entry.objects.filter(pk__in=school_ids, kind='school'):
                if not klass or school.name not in klass.data.get('allowed_schools', []):
                    raise ValueError('Выберите школу, доступную выбранному классу')
        creating = not c.pk
        c.revision += 1
        c.save()
        ids = p.get('abilities', [])
        if not isinstance(ids, list):
            raise ValueError('Некорректный список умений')
        c.abilities.set(Entry.objects.filter(id__in=ids, kind='ability', archived=False))
        if creating and p.get('campaign'):
            campaign = access_campaign(user, p['campaign'])
            campaign.players.add(c.owner)
            Membership.objects.create(character=c, campaign=campaign)
        if creating:
            c.runtime['hp'] = computed(c)['max_hp']
            c.save(update_fields=['runtime'])
        return {'id': c.id}
    if op == 'notes.private':
        c = get_object_or_404(Character, pk=p['id'], owner=user)
        if c.private_notes != p.get('base', ''):
            c.private_notes = merge_notes(p.get('base', ''), str(p.get('text', '')), c.private_notes)
        else:
            c.private_notes = str(p.get('text', ''))
        c.private_notes = c.private_notes[:50000]
        c.save(update_fields=['private_notes'])
        return {'text': c.private_notes}
    if op == 'campaign.join':
        campaign = get_object_or_404(Campaign, pk=p['campaign'])
        campaign.players.add(user)
        return {'id': campaign.id}
    if op == 'campaign.create':
        require_master(user)
        name = str(p.get('name', '')).strip()[:120]
        if not name:
            raise ValueError('Укажите название')
        c = Campaign.objects.create(name=name, description=str(p.get('description', ''))[:5000])
        c.players.add(user)
        Squad.objects.create(campaign=c, name='Основной отряд')
        return {'id': c.id}
    if op == 'squad.create':
        require_master(user)
        c = get_object_or_404(Campaign, pk=p['campaign'])
        name = str(p.get('name', '')).strip()[:100]
        if not name:
            raise ValueError('Укажите название')
        Squad.objects.create(campaign=c, name=name)
    elif op == 'membership':
        c = owned(user, p['character'])
        campaign = get_object_or_404(Campaign, pk=p['campaign'])
        if p.get('leave'):
            Membership.objects.filter(character=c, campaign=campaign).delete()
        else:
            squad = get_object_or_404(Squad, pk=p['squad'], campaign=campaign) if p.get('squad') else None
            Membership.objects.update_or_create(character=c, campaign=campaign, defaults={'squad': squad})
            campaign.players.add(c.owner)
    elif op == 'notes.shared':
        c = access_campaign(user, p['campaign'])
        text = str(p.get('text', ''))[:50000]
        base = str(p.get('base', ''))[:50000]
        c.notes = text if c.notes == base else merge_notes(base, text, c.notes)
        c.note_revision += 1
        c.save(update_fields=['notes', 'note_revision'])
        return {'text': c.notes}
    elif op == 'entry.save':
        require_master(user)
        entry = get_object_or_404(Entry, pk=p['id']) if p.get('id') else Entry()
        if p.get('archive'):
            entry.archived = True
        else:
            entry.kind = p['kind']
            if entry.kind not in dict(Entry.KINDS):
                raise ValueError('Неизвестный тип записи')
            entry.name = str(p['name']).strip()[:160]
            if not entry.name:
                raise ValueError('Укажите название')
            entry.description = str(p.get('description', ''))[:30000]
            data = p.get('data', {})
            if not isinstance(data, dict):
                raise ValueError('Параметры должны быть объектом')
            validate_entry(data)
            entry.data = data
        entry.save()
        return {'id': entry.id}
    elif op.startswith('item.'):
        item_action(user, p)
    elif op == 'session.create':
        require_master(user)
        squad = get_object_or_404(Squad, pk=p['squad'])
        chars = Character.objects.filter(id__in=p.get('characters', []), memberships__squad=squad).distinct()
        if not chars:
            raise ValueError('Выберите персонажей отряда')
        s = Session.objects.create(campaign=squad.campaign, squad=squad, name=str(p.get('name', 'Игровая встреча'))[:160])
        s.characters.set(chars)
        return {'id': s.id}
    elif op == 'scene.start':
        require_master(user)
        session = get_object_or_404(Session, pk=p['session'])
        chars = list(session.characters.all())
        if not chars:
            raise ValueError('В сессии нет персонажей')
        if any(current_scene(c) for c in chars):
            raise ValueError('Персонаж уже участвует в активном бою')
        order = [c.id for c in sorted(chars, key=lambda c: bounded(p.get('initiative', {}).get(str(c.id), 0), -1000, 1000), reverse=True)]
        scene = Scene.objects.create(session=session, state={'active': False, 'order': order, 'turn': 0, 'round': 1})
        change = Change(user, 'Начало боя · ' + session.name, scene)
        change.watch(scene).state['active'] = True
        for c in chars:
            change.watch(c)
            c.runtime.update(used={}, actions={**ACTIONS, 'reaction': computed(c)['reactions']}, turns=0)
        change.finish()
        return {'id': scene.id}
    elif op in ['scene.turn', 'scene.end']:
        scene = access_scene(user, p['scene'])
        if not scene.state.get('active'):
            raise ValueError('Бой уже завершён')
        if p.get('version') != scene.state:
            raise ValueError('Ход уже изменился. Повторите действие с актуальным состоянием.')
        order = scene.state['order']
        current = Character.objects.get(pk=order[scene.state['turn']])
        if op == 'scene.end':
            require_master(user)
        elif current.owner_id != user.id and not master(user):
            raise PermissionDenied('Это не ваш ход')
        change = Change(user, 'Конец боя' if op == 'scene.end' else 'Ход завершён · ' + current.name, scene)
        change.watch(scene)
        chars = {c.id: c for c in Character.objects.filter(id__in=order)}
        for c in chars.values():
            change.watch(c)
        if op == 'scene.end':
            scene.state['active'] = False
            for c in chars.values():
                c.runtime.update(effects=[], used={}, temp=0, actions=dict(ACTIONS))
                c.runtime['hp'] = computed(c)['max_hp']
        else:
            c = chars[current.id]
            c.runtime['turns'] = c.runtime.get('turns', 0) + 1
            effects = []
            for e in c.runtime.get('effects', []):
                if e.get('duration') == 'turns':
                    e['remaining'] -= 1
                    if e['remaining'] <= 0:
                        continue
                effects.append(e)
            c.runtime['effects'] = effects
            scene.state['turn'] = (scene.state['turn'] + 1) % len(order)
            if scene.state['turn'] == 0:
                scene.state['round'] += 1
                for c in chars.values():
                    c.runtime.setdefault('actions', {})['reaction'] = computed(c)['reactions']
            next_char = chars[order[scene.state['turn']]]
            next_char.runtime.setdefault('actions', {}).update(ACTIONS)
        change.finish()
    elif op == 'hp':
        require_master(user)
        c = get_object_or_404(Character, pk=p['character'])
        change = Change(user, 'Изменение ХП · ' + c.name, current_scene(c))
        change.watch(c)
        value = bounded(p.get('value'), 0, 100000)
        hp, temp = c.runtime.get('hp', 0), c.runtime.get('temp', 0)
        mode = p.get('mode')
        if mode == 'damage':
            c.runtime['temp'] = max(0, temp - value)
            c.runtime['hp'] = max(0, hp - max(0, value - temp))
        elif mode == 'heal':
            c.runtime['hp'] = min(computed(c)['max_hp'], hp + value)
        elif mode == 'temp':
            c.runtime['temp'] = max(temp, value)
        elif mode == 'temp_set':
            c.runtime['temp'] = value
        else:
            c.runtime['hp'] = min(computed(c)['max_hp'], value)
        change.finish()
    elif op in ['ability.use', 'aura.set']:
        use_ability(user, p)
    elif op == 'action.spend':
        c = owned(user, p['character'])
        scene = current_scene(c)
        if not scene or scene.state['order'][scene.state['turn']] != c.id:
            raise ValueError('Сейчас не ваш ход')
        change = Change(user, 'Действие · ' + c.name, scene)
        change.watch(c)
        key = p.get('action')
        if key not in ['main', 'minor', 'move'] or c.runtime.get('actions', {}).get(key, 0) < 1:
            raise ValueError('Действие недоступно')
        c.runtime['actions'][key] -= 1
        if p.get('exchange'):
            if key != 'main' or p['exchange'] not in ['minor', 'move']:
                raise ValueError('Можно обменять основное на малое или движение')
            c.runtime['actions'][p['exchange']] += 1
        change.finish()
    elif op in ['undo', 'redo']:
        undo(user, redo=op == 'redo')
    else:
        raise ValueError('Неизвестная операция')
    return {}


def validate_entry(d):
    for key in ['formula', 'dice', 'stat', 'source_name']:
        if key in d and not isinstance(d[key], str):
            raise ValueError('Параметр ' + key + ' должен быть строкой')
    for key in ['circle', 'crit', 'armor', 'hp_base', 'hp_level', 'speed']:
        if key in d:
            if type(d[key]) is not int:
                raise ValueError('Параметр ' + key + ' должен быть целым числом')
            bounded(d[key], 0, 1000)
    if 'circle' in d and int(d['circle']) > 3:
        raise ValueError('Круг: от 0 до 3')
    if d.get('action', 'main') not in ['main', 'minor', 'move', 'reaction', 'free']:
        raise ValueError('Некорректный тип действия')
    if d.get('category', 'active') not in ['active', 'passive', 'noncombat']:
        raise ValueError('Некорректная категория')
    for field in ['keywords', 'requires']:
        if field in d and (not isinstance(d[field], list) or any(not isinstance(x, str) for x in d[field])):
            raise ValueError('Ключевые слова должны быть списком строк')
    if not isinstance(d.get('effects', []), list):
        raise ValueError('Эффекты должны быть списком')
    for e in d.get('effects', []):
        if not isinstance(e, dict) or e.get('stat') not in ['hp', 'temp', 'hit', 'damage', 'ac', 'speed'] + [k for k, _ in STATS]:
            raise ValueError('Некорректный эффект')
        if type(e.get('value', 0)) is not int or type(e.get('turns', 3)) is not int:
            raise ValueError('Величина и длительность эффекта должны быть целыми числами')
        bounded(e.get('value', 0), -10000, 10000)
        if e.get('duration', 'turns') not in ['turns', 'battle', 'aura']:
            raise ValueError('Неизвестная длительность')
        bounded(e.get('turns', 3), 1, 100)


def item_action(user, p):
    op = p['op']
    item = get_object_or_404(Item, pk=p['id']) if p.get('id') else Item()
    if item.pk:
        owned(user, item.character_id) if item.character_id else access_campaign(user, item.campaign_id)
    if op == 'item.delete':
        item.delete()
        return
    if op == 'item.transfer':
        if p.get('character'):
            c = owned(user, p['character'])
            if item.campaign_id:
                if not c.memberships.filter(campaign_id=item.campaign_id).exists():
                    raise ValueError('Персонаж не участвует в этой кампании')
            item.character, item.campaign = c, None
        else:
            campaign = access_campaign(user, p['campaign'])
            if item.character_id and not item.character.memberships.filter(campaign=campaign).exists():
                raise ValueError('Персонаж не участвует в этой кампании')
            item.character, item.campaign = None, campaign
        item.equipped = False
    else:
        if not item.pk:
            if p.get('character'):
                item.character = owned(user, p['character'])
            else:
                item.campaign = access_campaign(user, p['campaign'])
        if item.character_id and current_scene(item.character):
            raise ValueError('В первой версии меняйте экипировку вне боя; действия смены оружия появятся отдельно.')
        item.name = str(p.get('name', '')).strip()[:160]
        if not item.name:
            raise ValueError('Укажите предмет')
        item.quantity = bounded(p.get('quantity', 1), 1, 100000)
        item.equipped = bool(p.get('equipped')) if item.character_id else False
        item.slot = str(p.get('slot', ''))[:40]
        data = p.get('data', {})
        if not isinstance(data, dict):
            raise ValueError('Некорректные свойства')
        validate_entry(data)
        item.data = data
    item.save()


def use_ability(user, p):
    c = owned(user, p['character'])
    a = get_object_or_404(c.abilities, pk=p['ability'])
    scene = current_scene(c)
    if not scene:
        raise ValueError('Умение можно применить в активном бою')
    d = a.data
    aura = p['op'] == 'aura.set'
    if aura and not d.get('aura'):
        raise ValueError('Это не аура')
    if not aura:
        reason = availability(c, a, scene)
        if reason:
            raise ValueError(reason)
        needs_roll = rolls_required(a) or bool(a.data.get('weapon'))
        if needs_roll and not str(p.get('roll_result', '')).strip():
            raise ValueError('Введите результат физического броска. Действие пока не применено.')
    ids = list(dict.fromkeys(int(i) for i in p.get('targets', [])))
    if any(i not in scene.state['order'] for i in ids):
        raise ValueError('Выберите участников текущего боя')
    if d.get('effects') and not ids and not aura:
        raise ValueError('Выберите цель')
    if d.get('target') == 'single' and len(ids) > 1:
        raise ValueError('Выберите одну цель')
    change = Change(user, ('Получатели ауры · ' if aura else '') + a.name + ' · ' + c.name, scene,
                    inputs={'outcome': p.get('outcome'), 'roll_result': str(p.get('roll_result', ''))[:2000], 'targets': ids})
    change.watch(c)
    if not aura:
        act = d.get('action', 'main')
        if act != 'free':
            c.runtime['actions'][act] -= 1
        if not (p.get('outcome') == 'miss' and d.get('reliable')):
            used = c.runtime.setdefault('used', {})
            used[str(a.id)] = used.get(str(a.id), 0) + 1
    targets = {x.id: x for x in Character.objects.filter(id__in=scene.state['order'])}
    targets[c.id] = c
    if aura:
        for t in targets.values():
            change.watch(t)
            t.runtime['effects'] = [e for e in t.runtime.get('effects', []) if e.get('aura_source') != f'{c.id}:{a.id}']
    if p.get('outcome') != 'miss' or aura:
        for pk in ids:
            t = change.watch(targets[pk])
            for index, e in enumerate(d.get('effects', [])):
                if e.get('manual'):
                    continue
                value = int(e.get('value', 0))
                if e['stat'] in ['hp', 'temp']:
                    if aura:
                        continue
                    if e['stat'] == 'hp':
                        t.runtime['hp'] = min(computed(t)['max_hp'], t.runtime.get('hp', 0) + max(0, value))
                    else:
                        t.runtime['temp'] = max(t.runtime.get('temp', 0), value)
                else:
                    effect = {'key': e.get('key') or f'{a.id}:{index}', 'name': e.get('name', a.name),
                              'stat': e['stat'], 'value': value, 'keyword': e.get('keyword', ''),
                              'source': c.name, 'source_id': c.id, 'ability_id': a.id,
                              'duration': 'aura' if aura else e.get('duration', 'turns'),
                              'remaining': int(e.get('turns', 3))}
                    if aura:
                        effect.update(key=f'aura:{c.id}:{a.id}:{index}', aura_source=f'{c.id}:{a.id}')
                    put_effect(t, effect)
    change.finish()


@login_required
@require_POST
def action(request):
    try:
        p = json.loads(request.body)
        if not isinstance(p, dict):
            raise ValueError('Некорректный запрос')
        key = str(p.get('key', ''))
        uuid.UUID(key)
        with transaction.atomic():
            Clock.objects.get_or_create(pk=1)
            clock = Clock.objects.select_for_update().get(pk=1)
            receipt = Receipt.objects.filter(actor=request.user, key=key).first()
            if receipt:
                return JsonResponse(receipt.result)
            result = {'ok': True, **execute(request.user, p)}
            clock.revision += 1
            clock.save(update_fields=['revision'])
            Receipt.objects.create(actor=request.user, key=key, result=result)
        return JsonResponse(result)
    except PermissionDenied as e:
        return JsonResponse({'error': str(e)}, status=403)
    except (ValueError, TypeError, KeyError, ValidationError) as e:
        return JsonResponse({'error': str(e) or 'Проверьте введённые данные'}, status=400)


@login_required
@require_POST
def photo(request, pk):
    c = owned(request.user, pk)
    f = request.FILES.get('photo')
    if not f or f.size > 5 * 1024 * 1024:
        return HttpResponseBadRequest('Изображение должно быть не больше 5 МБ')
    try:
        img = Image.open(f)
        if img.width * img.height > 25000000:
            raise ValueError()
        img = ImageOps.exif_transpose(img).convert('RGB')
        img.thumbnail((1000, 1000))
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85)
    except Exception:
        return HttpResponseBadRequest('Не удалось прочитать изображение')
    with transaction.atomic():
        clock = Clock.objects.select_for_update().get(pk=1)
        c.photo.save(f'{uuid.uuid4()}.jpg', ContentFile(output.getvalue()))
        clock.revision += 1
        clock.save()
    return JsonResponse({'ok': True})


@login_required
def portrait(request, pk):
    c = get_object_or_404(Character, pk=pk)
    if not c.photo:
        return HttpResponseBadRequest('Нет фотографии')
    return FileResponse(c.photo.open('rb'), content_type='image/jpeg')
