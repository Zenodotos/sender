import logging
import time
import random
from django.core.mail import send_mail
from django.conf import settings
import re

logger = logging.getLogger(__name__)


class MessageSender:
    """Service do wysyłania wiadomości email i SMS"""
    
    def __init__(self):
        # Wybierz provider SMS na podstawie konfiguracji
        if hasattr(settings, 'SMSAPI_TOKEN') and settings.SMSAPI_TOKEN:
            print("Using SMSAPI provider for SMS")
            self.sms_provider = SMSAPIProvider()
        else:
            print("Using mock SMS provider")
            self.sms_provider = MockSMSProvider()
            
        # Email provider
        if hasattr(settings, 'EMAIL_BACKEND') and 'console' not in settings.EMAIL_BACKEND:
            self.email_provider = DjangoEmailProvider()
        else:
            self.email_provider = MockEmailProvider()
    
    def send_email(self, to_email, subject, message):
        """
        Wyślij email
        
        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        return self.email_provider.send(to_email, subject, message)
    
    def send_sms(self, to_phone, message):
        """
        Wyślij SMS
        
        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        return self.sms_provider.send(to_phone, message)


class SMSAPIProvider:
    """Provider SMS używający SMSAPI - zgodnie z oficjalną dokumentacją"""
    
    def __init__(self):
        try:
            from smsapi.client import SmsApiPlClient
            from smsapi.exception import SmsApiException
            
            self.client = SmsApiPlClient(access_token=settings.SMSAPI_TOKEN)
            self.SmsApiException = SmsApiException
            logger.info("SMSAPI provider initialized successfully")
        except ImportError:
            logger.error("smsapi-client not installed. Run: pip install smsapi-client")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize SMSAPI: {str(e)}")
            raise
    
    def send(self, to_phone, message):
        """
        Wyślij SMS przez SMSAPI - zgodnie z dokumentacją
        
        Args:
            to_phone (str): Numer telefonu odbiorcy
            message (str): Treść wiadomości
            
        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        try:
            # Walidacja numeru telefonu
            if not self._validate_phone(to_phone):
                return False, "Nieprawidłowy numer telefonu"
            
            # Przygotuj numer telefonu
            clean_phone = self._clean_phone_number(to_phone)
            
            # Wyślij SMS zgodnie z dokumentacją: client.sms.send(to="phone number", message="text message")
            send_results = self.client.sms.send(to=clean_phone, message=message, encoding='UTF8')
            
            # Obsłuż wyniki zgodnie z dokumentacją: for result in send_results: print(result.id, result.points, result.error)
            for result in send_results:
                if result.error:
                    logger.error(f"SMSAPI error for {clean_phone}: {result.error}")
                    return False, str(result.error)
                else:
                    logger.info(f"SMS sent successfully to {clean_phone} (ID: {result.id}, Points: {result.points})")
                    return True, None
            
            # Jeśli brak wyników
            return False, "Brak wyników wysyłania"
                
        except self.SmsApiException as e:
            # Obsługa wyjątków zgodnie z dokumentacją: except SmsApiException as e: print(e.message, e.code)
            logger.error(f"SMSAPI exception: {e.message} (code: {e.code})")
            return False, f"SMSAPI: {e.message}"
        except Exception as e:
            logger.error(f"Error sending SMS via SMSAPI: {str(e)}")
            return False, f"Błąd: {str(e)}"
    
    def _validate_phone(self, phone):
        """Walidacja numeru telefonu"""
        clean_phone = re.sub(r'[^\d\+]', '', phone)
        digits_only = re.sub(r'[^\d]', '', clean_phone)
        return len(digits_only) >= 9
    
    def _clean_phone_number(self, phone):
        """Czyści i formatuje numer telefonu"""
        clean = re.sub(r'[^\d\+]', '', phone)
        
        if not clean.startswith('+'):
            if clean.startswith('48'):
                clean = '+' + clean
            elif clean.startswith('0'):
                clean = '+48' + clean[1:]
            else:
                clean = '+48' + clean
        
        return clean


class MockSMSProvider:
    """Mock provider SMS dla testów (istniejący kod)"""
    
    def send(self, to_phone, message):
        """Mock wysyłanie SMS dla testów"""
        # Walidacja numeru telefonu
        if not self._validate_phone(to_phone):
            return False, "Nieprawidłowy numer telefonu"
        
        # Sprawdź długość wiadomości
        if len(message) > 160:
            logger.warning(f"SMS message longer than 160 characters: {len(message)}")
        
        # Symulacja opóźnienia wysyłania
        time.sleep(random.uniform(0.2, 0.8))
        
        # Symulacja różnych scenariuszy
        if 'fail' in to_phone:
            return False, "Numer telefonu odrzucony przez operatora"
        elif to_phone.startswith('000'):
            return False, "Nieprawidłowy numer telefonu"
        elif random.random() < 0.03:  # 3% szans na błąd
            return False, "Tymczasowy błąd sieci SMS"
        else:
            logger.info(f"[MOCK] SMS sent to {to_phone}: {message[:50]}...")
            return True, None
    
    def _validate_phone(self, phone):
        """Walidacja numeru telefonu"""
        # Usuń wszystko oprócz cyfr i znaku +
        clean_phone = re.sub(r'[^\d\+]', '', phone)
        
        # Sprawdź czy ma przynajmniej 9 cyfr
        digits_only = re.sub(r'[^\d]', '', clean_phone)
        return len(digits_only) >= 9


class DjangoEmailProvider:
    """Provider email używający Django (prawdziwy wysył)"""
    
    def send(self, to_email, subject, message):
        """Wyślij email przez Django"""
        try:
            # Walidacja email
            if not self._validate_email(to_email):
                return False, "Nieprawidłowy adres email"
            
            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
                recipient_list=[to_email],
                fail_silently=False,
            )
            logger.info(f"Email sent successfully to {to_email}")
            return True, None
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False, f"Błąd wysyłania: {str(e)}"
    
    def _validate_email(self, email):
        """Walidacja adresu email"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None


class MockEmailProvider:
    """Mock provider email dla testów (istniejący kod)"""
    
    def send(self, to_email, subject, message):
        """Mock wysyłanie emaila dla testów"""
        # Walidacja email
        if not self._validate_email(to_email):
            return False, "Nieprawidłowy adres email"
        
        # Symulacja opóźnienia wysyłania
        time.sleep(random.uniform(0.1, 0.5))
        
        # Symulacja różnych scenariuszy
        if 'fail@' in to_email.lower():
            return False, "Adres email odrzucony przez serwer"
        elif 'invalid@' in to_email.lower():
            return False, "Nieprawidłowy adres email"
        elif random.random() < 0.05:  # 5% szans na błąd
            return False, "Tymczasowy błąd serwera email"
        else:
            logger.info(f"[MOCK] Email sent to {to_email} with subject: {subject}")
            return True, None
    
    def _validate_email(self, email):
        """Walidacja adresu email"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None


# Przykłady konfiguracji dla settings.py (zakomentowane)

"""
# SMSAPI Configuration
SMSAPI_TOKEN = 'your-smsapi-token-here'  # Token z panelu SMSAPI
SMSAPI_FROM = 'FIRMA'  # Nadawca SMS (max 11 znaków) lub 'ECO' dla tanich SMS

# Email Configuration  
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'
DEFAULT_FROM_EMAIL = 'your-email@gmail.com'
"""