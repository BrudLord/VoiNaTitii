from django.conf import settings
from django.db import models


class Clock(models.Model):
    revision = models.PositiveBigIntegerField(default=0)


class Entry(models.Model):
    KINDS = [(k, v) for k, v in [('ability', 'Умение'), ('item', 'Снаряжение'), ('race', 'Раса'),
             ('class', 'Класс'), ('school', 'Школа'), ('background', 'Предыстория'), ('craft', 'Ремесло'),
             ('keyword', 'Ключевое слово'), ('specialization', 'Специализация'), ('effect', 'Эффект')]]
    kind = models.CharField(max_length=30, choices=KINDS)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    data = models.JSONField(default=dict, blank=True)
    archived = models.BooleanField(default=False)
    source = models.CharField(max_length=200, blank=True)

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
