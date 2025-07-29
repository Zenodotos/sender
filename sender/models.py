from django.db import models
import uuid
import json


class Campaign(models.Model):
    """Model reprezentujący pojedynczą kampanię wysyłki"""
    uid = models.UUIDField(default=uuid.uuid4, primary_key=True)
    name = models.CharField(max_length=100, verbose_name="Nazwa kampanii")
    message_content = models.TextField(verbose_name="Treść wiadomości")
    message_type = models.CharField(
        max_length=10,
        choices=[('email', 'Email'), ('sms', 'SMS'), ('both', 'Email i SMS')],
        verbose_name="Typ wiadomości"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    
    # Metadata z Excela - dodatkowe kolumny jako JSON
    excel_columns = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.get_message_type_display()})"


class Recipient(models.Model):
    """Model reprezentujący odbiorcę w ramach kampanii"""
    STATUS_CHOICES = [
        ('pending', 'Oczekuje'),
        ('sent', 'Wysłane'),
        ('failed', 'Błąd'),
        ('skipped', 'Pominięte')
    ]
    
    uid = models.UUIDField(default=uuid.uuid4, primary_key=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='recipients')
    
    # Podstawowe dane
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(max_length=254, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)  # Zwiększone dla numerów międzynarodowych
    
    # Dodatkowe dane z Excela jako JSON
    extra_data = models.JSONField(default=dict, blank=True)
    
    # Status wysyłki
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    
    class Meta:
        unique_together = ['campaign', 'email', 'phone']  # Zapobiega duplikatom w ramach kampanii
    
    def __str__(self):
        contact = self.email or self.phone or "Brak kontaktu"
        return f"{self.first_name} {self.last_name} ({contact})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    def get_message_variables(self):
        """Zwraca wszystkie dostępne zmienne do podstawienia w wiadomości"""
        variables = {
            'first_name': self.first_name,
            'last_name': self.last_name,
            'full_name': self.full_name,
            'email': self.email,
            'phone': self.phone,
        }
        # Dodaj zmienne z extra_data
        variables.update(self.extra_data)
        return variables


class MessageLog(models.Model):
    """Log szczegółowy dla każdej próby wysłania wiadomości"""
    MESSAGE_TYPES = [
        ('email', 'Email'),
        ('sms', 'SMS')
    ]
    
    uid = models.UUIDField(default=uuid.uuid4, primary_key=True)
    recipient = models.ForeignKey(Recipient, on_delete=models.CASCADE, related_name='message_logs')
    message_type = models.CharField(max_length=5, choices=MESSAGE_TYPES)
    
    # Treść wiadomości po podstawieniu zmiennych
    final_message = models.TextField()
    
    # Status
    success = models.BooleanField()
    sent_at = models.DateTimeField(auto_now_add=True)
    error_details = models.TextField(blank=True, null=True)
    
    # Metadata providera (np. message ID z SMS gateway)
    provider_response = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        status = "✓" if self.success else "✗"
        return f"{status} {self.get_message_type_display()} → {self.recipient}"


# Pomocnicze modele dla konfiguracji providerów

class SMSProvider(models.Model):
    """Konfiguracja providerów SMS"""
    name = models.CharField(max_length=50)
    class_name = models.CharField(max_length=100)  # np. 'providers.sms.TwilioSMS'
    is_active = models.BooleanField(default=True)
    config = models.JSONField(default=dict)  # API keys, URLs itp.
    
    def __str__(self):
        return self.name


class EmailProvider(models.Model):
    """Konfiguracja providerów Email"""
    name = models.CharField(max_length=50)
    class_name = models.CharField(max_length=100)  # np. 'providers.email.SMTPEmail'
    is_active = models.BooleanField(default=True)
    config = models.JSONField(default=dict)  # SMTP settings itp.
    
    def __str__(self):
        return self.name