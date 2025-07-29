from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count
from .models import Campaign, Recipient, MessageLog, SMSProvider, EmailProvider


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ['name', 'message_type', 'recipients_count', 'sent_count', 'failed_count', 'is_completed', 'created_at']
    list_filter = ['message_type', 'is_completed', 'created_at']
    search_fields = ['name', 'message_content']
    readonly_fields = ['uid', 'created_at', 'excel_columns']
    
    fieldsets = (
        ('Podstawowe Informacje', {
            'fields': ('uid', 'name', 'message_type', 'message_content')
        }),
        ('Status', {
            'fields': ('is_completed', 'created_at', 'sent_at')
        }),
        ('Dane z Excel', {
            'fields': ('excel_columns',),
            'classes': ('collapse',)
        }),
    )
    
    def recipients_count(self, obj):
        count = obj.recipients.count()
        url = reverse('admin:sender_recipient_changelist') + f'?campaign__uid__exact={obj.uid}'
        return format_html('<a href="{}">{}</a>', url, count)
    recipients_count.short_description = 'Odbiorcy'
    
    def sent_count(self, obj):
        count = obj.recipients.filter(status='sent').count()
        return format_html('<span style="color: green;">{}</span>', count)
    sent_count.short_description = 'Wysłane'
    
    def failed_count(self, obj):
        count = obj.recipients.filter(status='failed').count()
        if count > 0:
            return format_html('<span style="color: red;">{}</span>', count)
        return count
    failed_count.short_description = 'Błędy'
    
    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            recipients_total=Count('recipients')
        )


@admin.register(Recipient)
class RecipientAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'email', 'phone', 'campaign', 'status', 'sent_at']
    list_filter = ['status', 'campaign__name', 'sent_at']
    search_fields = ['first_name', 'last_name', 'email', 'phone']
    readonly_fields = ['uid']
    
    fieldsets = (
        ('Podstawowe Dane', {
            'fields': ('uid', 'campaign', 'first_name', 'last_name', 'email', 'phone')
        }),
        ('Status Wysyłki', {
            'fields': ('status', 'sent_at', 'error_message')
        }),
        ('Dodatkowe Dane', {
            'fields': ('extra_data',),
            'classes': ('collapse',)
        }),
    )
    
    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    full_name.short_description = 'Imię i Nazwisko'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('campaign')


@admin.register(MessageLog)
class MessageLogAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'message_type', 'success', 'sent_at']
    list_filter = ['message_type', 'success', 'sent_at']
    search_fields = ['recipient__first_name', 'recipient__last_name', 'recipient__email']
    readonly_fields = ['uid', 'sent_at']
    
    fieldsets = (
        ('Podstawowe Informacje', {
            'fields': ('uid', 'recipient', 'message_type', 'success', 'sent_at')
        }),
        ('Treść Wiadomości', {
            'fields': ('final_message',)
        }),
        ('Szczegóły', {
            'fields': ('error_details', 'provider_response'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('recipient', 'recipient__campaign')


@admin.register(SMSProvider)
class SMSProviderAdmin(admin.ModelAdmin):
    list_display = ['name', 'class_name', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'class_name']
    
    fieldsets = (
        ('Podstawowe Informacje', {
            'fields': ('name', 'class_name', 'is_active')
        }),
        ('Konfiguracja', {
            'fields': ('config',),
            'description': 'Konfiguracja w formacie JSON (klucze API, URLs, etc.)'
        }),
    )


@admin.register(EmailProvider)
class EmailProviderAdmin(admin.ModelAdmin):
    list_display = ['name', 'class_name', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'class_name']
    
    fieldsets = (
        ('Podstawowe Informacje', {
            'fields': ('name', 'class_name', 'is_active')
        }),
        ('Konfiguracja', {
            'fields': ('config',),
            'description': 'Konfiguracja w formacie JSON (SMTP settings, API keys, etc.)'
        }),
    )


# Dostosowanie strony głównej admin
admin.site.site_header = "System Wysyłki - Panel Administracyjny"
admin.site.site_title = "System Wysyłki"
admin.site.index_title = "Zarządzanie Kampaniami"