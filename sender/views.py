from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.utils import timezone
from django.db.models import Count, Q
from django.contrib import messages
import pandas as pd
import json
import re
from datetime import datetime
import logging
from .models import Campaign, Recipient, MessageLog
from .services import MessageSender

logger = logging.getLogger(__name__)


def upload_view(request):
    """Główny widok do tworzenia nowej kampanii"""
    return render(request, 'sender/upload.html')


def campaigns_view(request):
    """Widok listy wszystkich kampanii"""
    campaigns = Campaign.objects.all().order_by('-created_at')
    
    # Dodaj statystyki do każdej kampanii
    for campaign in campaigns:
        # Oblicz statystyki
        recipients = campaign.recipients.all()
        campaign.total_recipients = recipients.count()
        campaign.sent_count = recipients.filter(status='sent').count()
        campaign.failed_count = recipients.filter(status='failed').count()
        campaign.pending_count = recipients.filter(status='pending').count()
        
        # Sprawdź czy kampania jest zakończona
        if campaign.pending_count == 0 and campaign.total_recipients > 0:
            if not campaign.is_completed:
                campaign.is_completed = True
                campaign.save()
    
    return render(request, 'sender/campaigns.html', {'campaigns': campaigns})


def campaign_status(request, campaign_id):
    """Szczegółowy widok statusu kampanii"""
    campaign = get_object_or_404(Campaign, uid=campaign_id)
    
    # Pobierz odbiorców z paginacją
    recipients_list = campaign.recipients.all().order_by('-sent_at', 'last_name', 'first_name')
    
    # Filtrowanie
    status_filter = request.GET.get('status')
    search_query = request.GET.get('search')
    
    if status_filter:
        recipients_list = recipients_list.filter(status=status_filter)
    
    if search_query:
        recipients_list = recipients_list.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query)
        )
    
    # Paginacja
    paginator = Paginator(recipients_list, 50)  # 50 odbiorców na stronę
    page_number = request.GET.get('page')
    recipients = paginator.get_page(page_number)
    
    # Dodaj spersonalizowane wiadomości dla każdego odbiorcy
    for recipient in recipients:
        # Sprawdź czy istnieje log wiadomości z finalną treścią
        message_log = recipient.message_logs.first()
        
        if message_log and message_log.final_message:
            # Użyj finalnej wiadomości z logu (już wysłanej)
            recipient.personalized_message = message_log.final_message
        else:
            # Wygeneruj wiadomość z podstawionymi zmiennymi
            variables = recipient.get_message_variables()
            
            personalized_message = campaign.message_content
            for var_name, var_value in variables.items():
                if var_value:
                    personalized_message = personalized_message.replace(
                        f'{{{{{var_name}}}}}', 
                        str(var_value)
                    )
            
            recipient.personalized_message = personalized_message
    
    # Statystyki
    all_recipients = campaign.recipients.all()
    stats = {
        'total': all_recipients.count(),
        'sent': all_recipients.filter(status='sent').count(),
        'failed': all_recipients.filter(status='failed').count(),
        'pending': all_recipients.filter(status='pending').count(),
        'skipped': all_recipients.filter(status='skipped').count(),
    }
    
    # Sprawdź czy kampania jest zakończona
    if stats['pending'] == 0 and stats['total'] > 0 and not campaign.is_completed:
        campaign.is_completed = True
        campaign.save()
    
    context = {
        'campaign': campaign,
        'recipients': recipients,
        'stats': stats
    }
    
    return render(request, 'sender/campaign_status.html', context)


@require_http_methods(["POST"])
def upload_excel(request):
    """AJAX endpoint do analizy pliku Excel"""
    try:
        if 'excel_file' not in request.FILES:
            return JsonResponse({'success': False, 'error': 'Brak pliku'})
        
        excel_file = request.FILES['excel_file']
        
        # Sprawdź rozmiar pliku (max 10MB)
        if excel_file.size > 10 * 1024 * 1024:
            return JsonResponse({'success': False, 'error': 'Plik jest za duży (max 10MB)'})
        
        # Sprawdź rozszerzenie
        if not excel_file.name.lower().endswith(('.xlsx', '.xls')):
            return JsonResponse({'success': False, 'error': 'Nieprawidłowy format pliku'})
        
        # Wczytaj Excel
        try:
            df = pd.read_excel(excel_file)
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Błąd odczytu pliku Excel: {str(e)}'})
        
        if df.empty:
            return JsonResponse({'success': False, 'error': 'Plik Excel jest pusty'})
        
        # Mapowanie kolumn - automatyczne wykrywanie z lepszą obsługą polskich nazw
        columns = df.columns.tolist()
        mapped_columns = {}
        
        # Inteligentne mapowanie kolumn
        for col in columns:
            col_lower = col.lower().strip()
            
            # Imię - rozszerzone o polskie nazwy
            if any(keyword in col_lower for keyword in ['imię', 'imie', 'first', 'name', 'first_name', 'firstname']):
                if 'first_name' not in mapped_columns:
                    mapped_columns['first_name'] = col
            
            # Nazwisko - rozszerzone o polskie nazwy
            elif any(keyword in col_lower for keyword in ['nazwisko', 'last', 'surname', 'last_name', 'lastname']):
                if 'last_name' not in mapped_columns:
                    mapped_columns['last_name'] = col
            
            # Email
            elif any(keyword in col_lower for keyword in ['email', 'e-mail', 'mail', '@']):
                if 'email' not in mapped_columns:
                    mapped_columns['email'] = col
            
            # Telefon - rozszerzone o polskie nazwy
            elif any(keyword in col_lower for keyword in ['telefon', 'phone', 'tel', 'mobile', 'komórka', 'komórki', 'gsm', 'numer']):
                if 'phone' not in mapped_columns:
                    mapped_columns['phone'] = col
        
        # Jeśli nie znaleziono automatycznie, spróbuj z pierwszymi kolumnami
        if 'first_name' not in mapped_columns and len(columns) > 0:
            mapped_columns['first_name'] = columns[0]
        if 'last_name' not in mapped_columns and len(columns) > 1:
            mapped_columns['last_name'] = columns[1]
        if 'email' not in mapped_columns:
            # Szukaj kolumny zawierającej znak @
            for col in columns:
                if df[col].astype(str).str.contains('@', na=False).any():
                    mapped_columns['email'] = col
                    break
        if 'phone' not in mapped_columns:
            # Szukaj kolumny zawierającej numery telefonów
            for col in columns:
                if df[col].astype(str).str.match(r'[\d\s\+\-\(\)]+', na=False).any():
                    mapped_columns['phone'] = col
                    break
        
        # Dodatkowe kolumny (poza podstawowymi)
        basic_columns = set(mapped_columns.values())
        extra_columns = [col for col in columns if col not in basic_columns]
        
        # Debug logging
        logger.info(f"Columns found: {columns}")
        logger.info(f"Mapped columns: {mapped_columns}")
        logger.info(f"Extra columns: {extra_columns}")
        
        # Przygotuj przykładowe dane (pierwsze 5 wierszy)
        sample_data = []
        for _, row in df.head(5).iterrows():
            row_data = {}
            for col in columns:
                value = row[col]
                # Konwertuj NaN na None/pusty string
                if pd.isna(value):
                    row_data[col] = ''
                else:
                    row_data[col] = str(value).strip()
            sample_data.append(row_data)
        
        response_data = {
            'success': True,
            'total_rows': len(df),
            'columns': columns,
            'mapped_columns': mapped_columns,
            'extra_columns': extra_columns,
            'sample_data': sample_data
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error in upload_excel: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Błąd serwera: {str(e)}'})


@require_http_methods(["POST"])
def create_campaign(request):
    """Endpoint do tworzenia kampanii"""
    try:
        # Sprawdź czy plik Excel został ponownie przesłany
        if 'excel_file' not in request.FILES:
            return JsonResponse({'success': False, 'error': 'Brak pliku Excel'})
        
        excel_file = request.FILES['excel_file']
        campaign_name = request.POST.get('campaign_name')
        message_type = request.POST.get('message_type')
        message_content = request.POST.get('message_content')
        
        # Walidacja
        if not all([campaign_name, message_type, message_content]):
            return JsonResponse({'success': False, 'error': 'Wszystkie pola są wymagane'})
        
        if message_type not in ['email', 'sms', 'both']:
            return JsonResponse({'success': False, 'error': 'Nieprawidłowy typ wiadomości'})
        
        # Wczytaj ponownie Excel
        df = pd.read_excel(excel_file)
        
        # Mapowanie kolumn (podobnie jak w upload_excel) - ulepszone
        columns = df.columns.tolist()
        mapped_columns = {}
        
        for col in columns:
            col_lower = col.lower().strip()
            if any(keyword in col_lower for keyword in ['imię', 'imie', 'first', 'name', 'first_name']):
                if 'first_name' not in mapped_columns:
                    mapped_columns['first_name'] = col
            elif any(keyword in col_lower for keyword in ['nazwisko', 'last', 'surname', 'last_name']):
                if 'last_name' not in mapped_columns:
                    mapped_columns['last_name'] = col
            elif any(keyword in col_lower for keyword in ['email', 'e-mail', 'mail']):
                if 'email' not in mapped_columns:
                    mapped_columns['email'] = col
            elif any(keyword in col_lower for keyword in ['telefon', 'phone', 'tel', 'mobile', 'komórka', 'komórki', 'gsm', 'numer']):
                if 'phone' not in mapped_columns:
                    mapped_columns['phone'] = col
        
        # Ustawienia domyślne jeśli nie znaleziono
        if 'first_name' not in mapped_columns and len(columns) > 0:
            mapped_columns['first_name'] = columns[0]
        if 'last_name' not in mapped_columns and len(columns) > 1:
            mapped_columns['last_name'] = columns[1]
        
        # Dodatkowe kolumny
        basic_columns = set(mapped_columns.values())
        extra_columns = [col for col in columns if col not in basic_columns]
        
        # Utwórz kampanię
        campaign = Campaign.objects.create(
            name=campaign_name,
            message_type=message_type,
            message_content=message_content,
            excel_columns=mapped_columns
        )
        
        # Dodaj odbiorców
        recipients_created = 0
        skipped_recipients = 0
        
        for _, row in df.iterrows():
            try:
                # Podstawowe dane
                first_name = str(row.get(mapped_columns.get('first_name', ''), '')).strip()
                last_name = str(row.get(mapped_columns.get('last_name', ''), '')).strip()
                email = str(row.get(mapped_columns.get('email', ''), '')).strip()
                phone = str(row.get(mapped_columns.get('phone', ''), '')).strip()
                
                # Sprawdź czy mamy minimum dane
                if not first_name and not last_name:
                    skipped_recipients += 1
                    continue
                
                # Walidacja email
                if email and email != 'nan':
                    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                    if not re.match(email_pattern, email):
                        email = None
                else:
                    email = None
                
                # Walidacja telefonu
                if phone and phone != 'nan':
                    # Usuń wszystko oprócz cyfr, + i spacji
                    phone = re.sub(r'[^\d\+\s\-\(\)]', '', phone)
                    if len(phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')) < 9:
                        phone = None
                else:
                    phone = None
                
                # Sprawdź czy mamy przynajmniej email lub telefon dla danego typu kampanii
                if message_type == 'email' and not email:
                    skipped_recipients += 1
                    continue
                elif message_type == 'sms' and not phone:
                    skipped_recipients += 1
                    continue
                elif message_type == 'both' and not email and not phone:
                    skipped_recipients += 1
                    continue
                
                # Dodatkowe dane
                extra_data = {}
                for col in extra_columns:
                    value = row.get(col, '')
                    if pd.notna(value):
                        extra_data[col] = str(value).strip()
                
                # Utwórz odbiorcę
                recipient = Recipient.objects.create(
                    campaign=campaign,
                    first_name=first_name or 'Brak',
                    last_name=last_name or 'Danych',
                    email=email,
                    phone=phone,
                    extra_data=extra_data
                )
                recipients_created += 1
                
            except Exception as e:
                logger.error(f"Error creating recipient: {str(e)}")
                skipped_recipients += 1
                continue
        
        return JsonResponse({
            'success': True,
            'campaign_id': str(campaign.uid),
            'recipients_created': recipients_created,
            'skipped_recipients': skipped_recipients,
            'total_rows': len(df)
        })
        
    except Exception as e:
        logger.error(f"Error in create_campaign: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Błąd serwera: {str(e)}'})


@require_http_methods(["POST"])
def send_campaign(request, campaign_id):
    """Endpoint do wysyłania kampanii"""
    try:
        campaign = get_object_or_404(Campaign, uid=campaign_id)
        
        if campaign.is_completed:
            return JsonResponse({'success': False, 'error': 'Kampania została już wysłana'})
        
        # Pobierz odbiorców oczekujących
        pending_recipients = campaign.recipients.filter(status='pending')
        
        if not pending_recipients.exists():
            return JsonResponse({'success': False, 'error': 'Brak odbiorców do wysłania'})
        
        # Utwórz instancję serwisu wysyłania
        sender = MessageSender()
        
        # Rezultaty
        results = {
            'sent': 0,
            'failed': 0,
            'skipped': 0
        }
        
        # Wysyłaj wiadomości
        for recipient in pending_recipients:
            try:
                # Przygotuj zmienne do podstawienia
                variables = recipient.get_message_variables()
                
                # Podstaw zmienne w treści wiadomości
                message = campaign.message_content
                for var_name, var_value in variables.items():
                    if var_value:
                        message = message.replace(f'{{{{{var_name}}}}}', str(var_value))
                
                # Wyślij wiadomość w zależności od typu kampanii
                success = False
                error_message = None
                
                if campaign.message_type == 'email' and recipient.email:
                    success, error_message = sender.send_email(
                        recipient.email, 
                        campaign.name, 
                        message
                    )
                elif campaign.message_type == 'sms' and recipient.phone:
                    success, error_message = sender.send_sms(recipient.phone, message)
                elif campaign.message_type == 'both':
                    # Wysyłaj email i SMS
                    email_success = False
                    sms_success = False
                    errors = []
                    
                    if recipient.email:
                        email_success, email_error = sender.send_email(
                            recipient.email, 
                            f'{campaign.name}', 
                            message
                        )
                        if not email_success and email_error:
                            errors.append(f"Email: {email_error}")
                    
                    if recipient.phone:
                        sms_success, sms_error = sender.send_sms(recipient.phone, message)
                        if not sms_success and sms_error:
                            errors.append(f"SMS: {sms_error}")
                    
                    success = email_success or sms_success
                    error_message = '; '.join(errors) if errors else None
                
                # Aktualizuj status odbiorcy
                if success:
                    recipient.status = 'sent'
                    recipient.sent_at = timezone.now()
                    recipient.error_message = None
                    results['sent'] += 1
                else:
                    recipient.status = 'failed'
                    recipient.error_message = error_message or 'Nieznany błąd'
                    results['failed'] += 1
                
                recipient.save()
                
                # Utwórz log wiadomości
                if campaign.message_type in ['email', 'both'] and recipient.email:
                    MessageLog.objects.create(
                        recipient=recipient,
                        message_type='email',
                        final_message=message,
                        success=success
                    )
                
                if campaign.message_type in ['sms', 'both'] and recipient.phone:
                    MessageLog.objects.create(
                        recipient=recipient,
                        message_type='sms',
                        final_message=message,
                        success=success
                    )
                
            except Exception as e:
                logger.error(f"Error sending to recipient {recipient.uid}: {str(e)}")
                recipient.status = 'failed'
                recipient.error_message = f'Błąd serwera: {str(e)}'
                recipient.save()
                results['failed'] += 1
        
        # Sprawdź czy kampania jest zakończona
        remaining_pending = campaign.recipients.filter(status='pending').count()
        if remaining_pending == 0:
            campaign.is_completed = True
            campaign.sent_at = timezone.now()
            campaign.save()
        
        return JsonResponse({
            'success': True,
            'results': results,
            'campaign_completed': campaign.is_completed
        })
        
    except Exception as e:
        logger.error(f"Error in send_campaign: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Błąd serwera: {str(e)}'})


def api_campaign_status(request, campaign_id):
    """API endpoint dla real-time updates statusu kampanii"""
    try:
        campaign = get_object_or_404(Campaign, uid=campaign_id)
        
        # Pobierz aktualne statystyki
        recipients = campaign.recipients.all()
        stats = {
            'total': recipients.count(),
            'sent': recipients.filter(status='sent').count(),
            'failed': recipients.filter(status='failed').count(),
            'pending': recipients.filter(status='pending').count(),
            'skipped': recipients.filter(status='skipped').count(),
        }
        
        # Sprawdź czy kampania jest zakończona
        if stats['pending'] == 0 and stats['total'] > 0 and not campaign.is_completed:
            campaign.is_completed = True
            campaign.save()
        
        return JsonResponse({
            'success': True,
            'stats': stats,
            'campaign': {
                'name': campaign.name,
                'is_completed': campaign.is_completed,
                'sent_at': campaign.sent_at.isoformat() if campaign.sent_at else None
            }
        })
        
    except Exception as e:
        logger.error(f"Error in api_campaign_status: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})
    
def template(request):
    return render(request, 'sender/template.html')