# listings/tasks.py
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from .models import Payment

@shared_task
def send_payment_confirmation_email(payment_id):
    try:
        payment = Payment.objects.get(pk=payment_id)
        user = payment.user
        subject = f"Payment Confirmation for booking {payment.booking.id if payment.booking else ''}"
        message = (
            f"Hello {user.get_full_name() or user.username},\n\n"
            f"Your payment of {payment.amount} {payment.currency} has been received and confirmed.\n"
            f"Payment reference: {payment.chapa_reference}\n\n"
            "Thank you for booking with us."
        )
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
        return {"status": "sent", "payment_id": payment_id}
    except Exception as e:
        return {"status": "error", "error": str(e), "payment_id": payment_id}
