from django.db import models
from django.contrib.auth.models import User

class Listing(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2)
    location = models.CharField(max_length=255)
    host = models.ForeignKey(User, on_delete=models.CASCADE, related_name='listings')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Booking(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='bookings')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    check_in = models.DateField()
    check_out = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} booking for {self.listing.title}"

    def total_nights(self):
        return (self.check_out - self.check_in).days

    def total_amount(self):
        """Convenience: amount based on listing price and nights."""
        nights = self.total_nights()
        return (self.listing.price_per_night * nights) if nights > 0 else self.listing.price_per_night


class Review(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField()
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.rating} stars by {self.user.username}"


class Payment(models.Model):
    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="payments",
        null=True,
        blank=True,
        help_text="Optional link to the Booking this payment is for."
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="ETB")
    chapa_transaction_id = models.CharField(max_length=255, null=True, blank=True)
    chapa_reference = models.CharField(max_length=255, null=True, blank=True)
    checkout_url = models.URLField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    metadata = models.JSONField(null=True, blank=True)  # optional: store raw chapa metadata or booking info
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def mark_completed(self, txid=None):
        if txid:
            self.chapa_transaction_id = txid
        self.status = self.STATUS_COMPLETED
        self.save(update_fields=["chapa_transaction_id", "status", "updated_at"])

    def mark_failed(self):
        self.status = self.STATUS_FAILED
        self.save(update_fields=["status", "updated_at"])

    def mark_pending(self):
        self.status = self.STATUS_PENDING
        self.save(update_fields=["status", "updated_at"])

    def __str__(self):
        return f"Payment {self.pk} ({self.status}) - {self.amount} {self.currency}"
