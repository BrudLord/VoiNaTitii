from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from .models import Knowledge, Entry


def visible(character,user):
    rows=character.knowledge.all()
    if character.owner_id!=user.id:rows=rows.filter(private=False)
    return list(rows.values('id','kind','title','body','location','details','tags','private','archived','revision','entry_id'))


def save(user,p):
    from .views import owned
    record=get_object_or_404(Knowledge,pk=p['id']) if p.get('id') else Knowledge()
    character=owned(user,record.character_id if record.pk else p['character'])
    if record.pk and record.private and character.owner_id!=user.id:
        raise PermissionDenied('Личная запись доступна только владельцу персонажа')
    if record.pk and p.get('revision')!=record.revision:
        raise ValueError('Запись уже изменена. Обновите её перед сохранением; ваш текст остаётся в форме.')
    if p['op']=='knowledge.archive':
        if not record.pk:raise ValueError('Выберите запись')
        if type(p.get('archived')) is not bool:raise ValueError('Укажите состояние архива')
        record.archived=p['archived']
    else:
        kind=p.get('kind');private=p.get('private',True)
        if kind not in dict(Knowledge.KINDS):raise ValueError('Неизвестный раздел знаний')
        if type(private) is not bool:raise ValueError('Укажите видимость записи')
        if private and character.owner_id!=user.id:raise PermissionDenied('Личные записи создаёт только владелец персонажа')
        title=str(p.get('title','')).strip()
        if not title or len(title)>160:raise ValueError('Укажите название до 160 символов')
        tags=p.get('tags',[])
        if not isinstance(tags,list) or len(tags)>20 or any(not isinstance(t,str) or len(t)>40 for t in tags):raise ValueError('Не больше 20 меток по 40 символов')
        record.character=character;record.kind=kind;record.private=private;record.title=title
        for field,limit in [('body',30000),('location',200),('details',1000)]:
            value=p.get(field,'')
            if not isinstance(value,str) or len(value)>limit:raise ValueError('Слишком длинное поле: '+field)
            setattr(record,field,value)
        record.tags=list(dict.fromkeys(t.strip() for t in tags if t.strip()))
        record.entry=None
        if p.get('entry'):
            entry=get_object_or_404(Entry,pk=p['entry'],kind='ability',archived=False)
            if kind!='recipe' or entry.data.get('book_group')!='craft':raise ValueError('Выберите рецепт ремесла из книги')
            record.entry=entry
    if record.pk:record.revision+=1
    record.save()
    return {'id':record.id,'revision':record.revision}
