from django.conf import settings
from django.db import models


class Clock(models.Model):
    revision = models.PositiveBigIntegerField(default=0)


class Entry(models.Model):
    KINDS = [(k, v) for k, v in [('ability', 'Умение'), ('item', 'Снаряжение'), ('race', 'Раса'),
             ('class', 'Класс'), ('school', 'Школа'), ('background', 'Предыстория'), ('craft', 'Ремесло'),
             ('keyword', 'Ключевое слово'), ('specialization', 'Специализация'), ('effect', 'Эффект')]]
    source_entry = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='personal_versions')
    personal_character = models.ForeignKey('Character', null=True, blank=True, on_delete=models.CASCADE, related_name='personal_abilities')
    kind = models.CharField(max_length=30, choices=KINDS)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    data = models.JSONField(default=dict, blank=True)
    archived = models.BooleanField(default=False)
    source = models.CharField(max_length=200, blank=True)

    @property
    def display_name(self):
        return self.data.get('display_name',self.name) if self.personal_character_id else self.name

    def __str__(self):
        return self.name


class Character(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    level = models.PositiveSmallIntegerField(default=1)
    info = models.JSONField(default=dict)
    stats = models.JSONField(default=dict)
    abilities = models.ManyToManyField(Entry, blank=True, related_name='characters')
    runtime = models.JSONField(default=dict)
    private_notes = models.TextField(blank=True)
    photo = models.ImageField(upload_to='portraits/', blank=True)
    revision = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.name


class Campaign(models.Model):
    players = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='campaigns')
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    note_revision = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.name


class Squad(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='squads')
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Membership(models.Model):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name='memberships')
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='memberships')
    squad = models.ForeignKey(Squad, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['character', 'campaign'], name='one_membership')]


class Item(models.Model):
    character = models.ForeignKey(Character, null=True, blank=True, on_delete=models.CASCADE, related_name='items')
    campaign = models.ForeignKey(Campaign, null=True, blank=True, on_delete=models.CASCADE, related_name='items')
    entry = models.ForeignKey(Entry, null=True, blank=True, on_delete=models.SET_NULL)
    archived = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=160)
    quantity = models.PositiveIntegerField(default=1)
    equipped = models.BooleanField(default=False)
    slot = models.CharField(max_length=40, blank=True)
    data = models.JSONField(default=dict)

    class Meta:
        constraints = [models.CheckConstraint(condition=(models.Q(character__isnull=False, campaign__isnull=True) |
                       models.Q(character__isnull=True, campaign__isnull=False)), name='item_one_owner')]


class Session(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT)
    squad = models.ForeignKey(Squad, on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    characters = models.ManyToManyField(Character)
    created = models.DateTimeField(auto_now_add=True)


class Scene(models.Model):
    session = models.ForeignKey(Session, on_delete=models.PROTECT)
    state = models.JSONField(default=dict)
    created = models.DateTimeField(auto_now_add=True)


class Event(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    label = models.CharField(max_length=200)
    scene = models.ForeignKey(Scene, null=True, on_delete=models.PROTECT)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    inputs = models.JSONField(default=dict)
    undone = models.BooleanField(default=False)
    redoable = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)


class Receipt(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key = models.CharField(max_length=80)
    result = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['actor', 'key'], name='unique_command')]


class JournalEntry(models.Model):
    KINDS = [('quest', 'Квест'), ('note', 'Запись'), ('lore', 'Мир')]
    STATUSES = [('active', 'В работе'), ('done', 'Выполнено'), ('paused', 'Отложено'), ('failed', 'Провалено')]
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='journal')
    kind = models.CharField(max_length=10, choices=KINDS, default='quest')
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    person = models.CharField(max_length=160, blank=True)
    reward = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default='active')
    steps = models.JSONField(default=list, blank=True)
    tags = models.JSONField(default=list, blank=True)
    archived = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated', '-id']


class Knowledge(models.Model):
    KINDS = [('recipe', 'Рецепт'), ('contact', 'Контакт'), ('lore', 'Запись')]
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name='knowledge')
    entry = models.ForeignKey(Entry, null=True, blank=True, on_delete=models.SET_NULL)
    kind = models.CharField(max_length=12, choices=KINDS)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    details = models.CharField(max_length=1000, blank=True)
    tags = models.JSONField(default=list, blank=True)
    private = models.BooleanField(default=True)
    archived = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title', 'id']
