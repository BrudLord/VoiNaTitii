from django.contrib import admin
from .models import Entry, Character, Campaign, Squad, Session, Clock
from django.db.models import F


class RevisionAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        Clock.objects.get_or_create(pk=1)
        Clock.objects.filter(pk=1).update(revision=F('revision') + 1)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        Clock.objects.filter(pk=1).update(revision=F('revision') + 1)

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        Clock.objects.filter(pk=1).update(revision=F('revision') + 1)

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset)
        Clock.objects.filter(pk=1).update(revision=F('revision') + 1)

@admin.register(Entry)
class EntryAdmin(RevisionAdmin):
    list_display = ['name', 'kind', 'archived']
    list_filter = ['kind', 'archived']
    search_fields = ['name', 'description']

    def save_model(self, request, obj, form, change):
        from .views import validate_entry
        validate_entry(obj.data)
        super().save_model(request, obj, form, change)


@admin.register(Character)
class CharacterAdmin(RevisionAdmin):
    list_display = ['name', 'owner', 'level']
    search_fields = ['name', 'owner__username']
    exclude = ['private_notes']
    filter_horizontal = ['abilities']


admin.site.register(Campaign, RevisionAdmin)
admin.site.register(Squad, RevisionAdmin)
admin.site.register(Session, RevisionAdmin)

admin.site.site_header = 'Войны Стихий · Справочники'
