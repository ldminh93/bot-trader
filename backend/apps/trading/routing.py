from django.urls import path

from .consumers import BotConsumer

websocket_urlpatterns = [
    path("ws/bot/", BotConsumer.as_asgi()),
]

