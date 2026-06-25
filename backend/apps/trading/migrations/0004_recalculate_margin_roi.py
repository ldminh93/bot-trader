from decimal import Decimal

from django.db import migrations


def recalculate_margin_roi(apps, schema_editor):
    trade_model = apps.get_model("trading", "Trade")
    for trade in trade_model.objects.all().iterator():
        if trade.leverage <= 0 or trade.entry_price <= 0 or trade.quantity <= 0:
            trade.pnl_percent = Decimal("0")
        else:
            margin = (
                trade.entry_price
                * trade.quantity
                / Decimal(trade.leverage)
            )
            net_pnl = (
                trade.realized_pnl
                if trade.status == "CLOSED"
                else trade.realized_pnl + trade.unrealized_pnl
            )
            trade.pnl_percent = net_pnl / margin * Decimal("100")
        trade.save(update_fields=["pnl_percent"])


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0003_default_leverage_10"),
    ]

    operations = [
        migrations.RunPython(
            recalculate_margin_roi,
            migrations.RunPython.noop,
        ),
    ]
