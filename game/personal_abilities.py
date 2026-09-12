"""A character's edited ability never mutates the shared reference entry."""
import copy
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from .models import Entry
from .rules import current_scene


def save(user,p):
    from .views import owned,validate_entry
    c=owned(user,p['character'])
    if p.get('revision')!=c.revision:raise ValueError('Лист изменился; откройте умение снова')
    if current_scene(c):raise ValueError('Редактирование умения доступно после боя')
    original=get_object_or_404(Entry,pk=p['id'],kind='ability',archived=False)
    if not c.abilities.filter(pk=original.pk).exists() or original.personal_character_id not in [None,c.pk]:
        raise PermissionDenied('Персонаж не владеет этим умением')
    if original.data.get('system'):raise ValueError('Системное действие редактируется мастером в справочнике')
    data=p.get('data')
    if not isinstance(data,dict):raise ValueError('Параметры должны быть объектом')
    data=copy.deepcopy(data)
    if data.get('system'):raise ValueError('Личное умение не может быть системным')
    validate_entry(data)
    name=str(p.get('name','')).strip()[:160]
    if not name:raise ValueError('Укажите название')
    # Keep identity-based mechanics editable when the display name changes.
    from .weaponry import wide_swing_profile
    if 'wide_swing' not in data and wide_swing_profile(original) is not None:
        data['wide_swing']=wide_swing_profile(original)
    data['reviewed']=True
    data['display_name']=name
    entry=original if original.personal_character_id==c.pk else Entry(kind='ability',personal_character=c,source=original.source,source_entry=original)
    entry.name=original.name;entry.description=str(p.get('description',''))[:30000];entry.data=data;entry.save()
    if entry.pk!=original.pk:
        c.abilities.remove(original);c.abilities.add(entry)
    c.revision+=1;c.save(update_fields=['revision'])
    return {'id':entry.pk,'revision':c.revision}


def restore(user,p):
    from .views import owned
    c=owned(user,p['character'])
    if p.get('revision')!=c.revision:raise ValueError('Лист изменился; откройте умение снова')
    if current_scene(c):raise ValueError('Изменить версию умения можно после боя')
    personal=get_object_or_404(Entry,pk=p['id'],kind='ability',personal_character=c,archived=False)
    if not c.abilities.filter(pk=personal.pk).exists():raise ValueError('Это умение сейчас не изучено')
    source=Entry.objects.filter(pk=personal.source_entry_id,kind='ability',personal_character__isnull=True,archived=False).first()
    if not source:raise ValueError('Исходная запись больше недоступна в справочнике')
    c.abilities.remove(personal);c.abilities.add(source)
    c.revision+=1;c.save(update_fields=['revision'])
    return {'id':source.pk,'revision':c.revision}


def definition(entry):
    return {'id':entry.pk,'kind':entry.kind,'name':entry.display_name,'description':entry.description,
            'data':copy.deepcopy(entry.data),'personal':bool(entry.personal_character_id),'source_entry_id':entry.source_entry_id}
