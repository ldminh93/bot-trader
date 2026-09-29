from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Trade
from .services.excursion_service import finalize_trade_metrics


@receiver(post_save, sender=Trade)
def finalize_closed_trade_metrics(sender, instance, **kwargs):
    """Every close path (paper, live, manual, follower sync, auto-heal) saves
    the Trade with status CLOSED, so hooking the save covers them all without
    touching any trading service. Idempotent: live closes save realized_pnl in
    a second write, which recomputes R."""
    if instance.status == Trade.Status.CLOSED:
        finalize_trade_metrics(instance)
