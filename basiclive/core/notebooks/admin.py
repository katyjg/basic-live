from django.contrib import admin

from . import models


@admin.register(models.EntryType)
class EntryTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(models.Notebook)
class NotebookAdmin(admin.ModelAdmin):
    list_display = ('title', 'name', 'created', 'modified')
    list_filter = ('created', 'modified')
    search_fields = ('title', 'name', 'description', )


@admin.register(models.Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ('notebook', 'author', 'kind', 'created')
    list_filter = ('kind', 'created')
    search_fields = ('text', 'tags', 'notebook__title', 'notebook__name')


@admin.register(models.Annotation)
class AnnotationAdmin(admin.ModelAdmin):
    list_display = ('entry', 'author', 'created')
    list_filter = ('created',)
    search_fields = ('text', 'quote',)
