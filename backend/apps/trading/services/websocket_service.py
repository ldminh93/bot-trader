from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def broadcast_user_update(user_id: int, event_type: str, payload: dict) -> None:
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_{user_id}",
        {
            "type": "bot.update",
            "event": event_type,
            "payload": payload,
        },
    )

