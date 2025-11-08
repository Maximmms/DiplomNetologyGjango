from rest_framework.throttling import UserRateThrottle

class EmailSendThrottle(UserRateThrottle):
    """
    Ограничивает частоту отправки писем подтверждения.
    """
    scope = 'email_send'


class LoginThrottle(UserRateThrottle):
    """
    Ограничивает частоту попыток входа.
    """
    scope = 'login'


class ResendCodeThrottle(UserRateThrottle):
    """
    Ограничивает частоту повторной отправки кода подтверждения.
    """
    scope = 'resend_code'