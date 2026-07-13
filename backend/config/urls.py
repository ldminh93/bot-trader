from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.trading.urls")),
]

if settings.DEBUG:
    # Daphne (unlike `manage.py runserver`) never auto-serves static files,
    # so admin CSS/JS 404s unless staticfiles routes are wired in explicitly.
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    urlpatterns += staticfiles_urlpatterns()

