import os
import requests
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .models import Payment, Booking
from .serializers import InitiatePaymentSerializer
from .tasks import send_payment_confirmation_email

CHAPA_INIT_URL = "https://api.chapa.co/v1/transaction/initialize"
CHAPA_VERIFY_URL_TEMPLATE = "https://api.chapa.co/v1/transaction/verify/{reference}"

def _chapa_headers():
    key = os.environ.get("CHAPA_SECRET_KEY") or getattr(settings, "CHAPA_SECRET_KEY", None)
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


class InitiatePaymentAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = InitiatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking_id = serializer.validated_data["booking_id"]
        amount = serializer.validated_data["amount"]
        currency = serializer.validated_data.get("currency", "ETB")
        return_url = serializer.validated_data.get("return_url")

        try:
            booking = Booking.objects.get(pk=booking_id, user=request.user)
        except Booking.DoesNotExist:
            return Response({"detail": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        payment = Payment.objects.create(
            booking=booking,
            user=request.user,
            amount=amount,
            currency=currency,
            status=Payment.STATUS_PENDING,
            metadata={"booking_id": booking.id}
        )

        payload = {
            "amount": str(amount),
            "currency": currency,
            "first_name": request.user.first_name or "",
            "last_name": request.user.last_name or "",
            "email": request.user.email,
            "tx_ref": f"booking-{booking.id}-payment-{payment.id}",
            "callback_url": return_url or request.build_absolute_uri(f"/api/payments/verify/?payment_id={payment.id}"),
            "metadata": {"booking_id": str(booking.id), "payment_id": str(payment.id)},
        }

        try:
            resp = requests.post(CHAPA_INIT_URL, json=payload, headers=_chapa_headers(), timeout=15)
            resp.raise_for_status()
            resp_data = resp.json()
        except requests.RequestException as e:
            payment.mark_failed()
            return Response({"detail": "Failed to initialize payment with Chapa.", "error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        chapa_data = resp_data.get("data") or {}
        checkout_url = chapa_data.get("checkout_url")
        chapa_ref = chapa_data.get("reference") or chapa_data.get("id") or payload.get("tx_ref")

        payment.checkout_url = checkout_url
        payment.chapa_reference = chapa_ref
        payment.metadata = {**(payment.metadata or {}), "chapa_response": chapa_data}
        payment.save(update_fields=["checkout_url", "chapa_reference", "metadata", "updated_at"])

        return Response({
            "checkout_url": checkout_url,
            "payment_id": payment.id,
            "chapa_reference": chapa_ref
        }, status=status.HTTP_201_CREATED)


class VerifyPaymentAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        reference = request.query_params.get("reference")
        payment_id = request.query_params.get("payment_id")

        if not reference and not payment_id:
            return Response({"detail": "reference or payment_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if payment_id:
                payment = Payment.objects.get(pk=payment_id)
                reference = payment.chapa_reference
            else:
                payment = Payment.objects.filter(chapa_reference=reference).first()
                if not payment:
                    return Response({"detail": "Payment not found for provided reference."}, status=status.HTTP_404_NOT_FOUND)
        except Payment.DoesNotExist:
            return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)

        verify_url = CHAPA_VERIFY_URL_TEMPLATE.format(reference=reference)
        try:
            resp = requests.get(verify_url, headers=_chapa_headers(), timeout=15)
            resp.raise_for_status()
            resp_data = resp.json()
        except requests.RequestException as e:
            return Response({"detail": "Failed to verify payment with Chapa.", "error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        chapa_data = resp_data.get("data") or {}
        txn_status = (chapa_data.get("status") or resp_data.get("status") or "").lower()
        txn_id = chapa_data.get("id") or chapa_data.get("transaction_id") or chapa_data.get("tx_id")

        if txn_status in ["success", "successful", "completed", "paid"]:
            payment.mark_completed(txid=txn_id)
            try:
                send_payment_confirmation_email.delay(payment.id)
            except Exception:
                pass
            return Response({"detail": "Payment completed", "payment_id": payment.id}, status=status.HTTP_200_OK)
        else:
            payment.mark_failed()
            return Response({"detail": "Payment not completed", "status": txn_status, "payment_id": payment.id}, status=status.HTTP_200_OK)
