from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


@database_sync_to_async
def get_user(token: str):
    try:
        validated = JWTAuthentication().get_validated_token(token)
        return JWTAuthentication().get_user(validated)
    except (InvalidToken, TokenError):
        return AnonymousUser()


class JWTAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = query.get("token", [""])[0]
        scope["user"] = await get_user(token) if token else AnonymousUser()
        return await self.app(scope, receive, send)

