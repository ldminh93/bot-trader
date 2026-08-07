from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.trading.models import BotLog, TradingBotConfig
from apps.trading.tasks import MAX_CONCURRENT_BOT_CYCLES, run_active_bots


def _make_configs(count: int) -> list[TradingBotConfig]:
    user = get_user_model().objects.create_user("active-bots@example.com", password="secure-pass")
    return [
        TradingBotConfig.objects.create(user=user, symbol=f"SYM{i}USDT", is_running=True)
        for i in range(count)
    ]


@pytest.mark.django_db
@patch("apps.trading.tasks.redis_client")
@patch("apps.trading.tasks.process_config")
def test_run_active_bots_processes_every_running_config(mock_process, mock_redis):
    """
    Reproduces the reported bug: with many scanner coins, a purely sequential
    loop takes roughly N x one-config's latency, which past a few dozen configs
    exceeds the beat schedule's interval and backs up Celery indefinitely.
    Processing configs concurrently (bounded by MAX_CONCURRENT_BOT_CYCLES) must
    still cover every running config, just not one-at-a-time.
    """
    configs = _make_configs(MAX_CONCURRENT_BOT_CYCLES * 2)
    mock_redis.set.return_value = True

    run_active_bots()

    assert mock_process.call_count == len(configs)
    processed_pks = {call.args[0].pk for call in mock_process.call_args_list}
    assert processed_pks == {config.pk for config in configs}


@pytest.mark.django_db
@patch("apps.trading.tasks.redis_client")
@patch("apps.trading.tasks.process_config")
def test_run_active_bots_skips_config_already_locked(mock_process, mock_redis):
    """A config whose Redis lock is already held (a previous cycle still running)
    must be skipped this tick, not processed twice concurrently."""
    locked, free = _make_configs(2)
    mock_redis.set.side_effect = lambda key, *a, **k: key != f"trading:cycle:{locked.pk}"

    run_active_bots()

    processed_pks = {call.args[0].pk for call in mock_process.call_args_list}
    assert processed_pks == {free.pk}


@pytest.mark.django_db(transaction=True)
@patch("apps.trading.tasks.redis_client")
@patch("apps.trading.tasks.process_config")
def test_run_active_bots_isolates_per_config_failures(mock_process, mock_redis):
    """One config's cycle failing must not prevent the others from running or
    from having their lock released — matches the original per-config isolation,
    now verified under concurrent execution."""
    failing, healthy = _make_configs(2)
    mock_redis.set.return_value = True

    def _side_effect(config):
        if config.pk == failing.pk:
            raise RuntimeError("upstream market-data error")

    mock_process.side_effect = _side_effect

    run_active_bots()

    assert mock_process.call_count == 2
    log = BotLog.objects.get(symbol=failing.symbol, level=BotLog.Level.ERROR)
    assert "upstream market-data error" in log.message
    # Lock release (the eval del-if-owner script) attempted for both configs,
    # including the one whose process_config call raised.
    assert mock_redis.eval.call_count == 2


@pytest.mark.django_db
@patch("apps.trading.tasks.process_config")
def test_run_active_bots_does_nothing_when_no_configs_running(mock_process):
    get_user_model().objects.create_user("idle-bots@example.com", password="secure-pass")

    run_active_bots()

    mock_process.assert_not_called()
