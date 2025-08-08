This project integrates the [Chapa API](https://developer.chapa.co/) into the Django-based My Travel App to allow users to make secure payments for bookings.  
Features include:

- Payment initiation with Chapa
- Payment verification
- Payment status tracking (`pending`, `completed`, `failed`)
- Email confirmation after successful payment (via Celery or console backend)
- Sandbox testing support
