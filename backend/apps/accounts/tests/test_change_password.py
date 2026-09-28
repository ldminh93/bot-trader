import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_change_password_succeeds_with_correct_current_password():
    user = get_user_model().objects.create_user("user@example.com", password="old-password1")
    client = APIClient()
    client.force_authenticate(user)

    response = client.post(
        "/api/auth/change-password",
        {"current_password": "old-password1", "new_password": "new-password1"},
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password("new-password1")


@pytest.mark.django_db
def test_change_password_rejects_wrong_current_password():
    user = get_user_model().objects.create_user("user@example.com", password="old-password1")
    client = APIClient()
    client.force_authenticate(user)

    response = client.post(
        "/api/auth/change-password",
        {"current_password": "wrong-password", "new_password": "new-password1"},
    )

    assert response.status_code == 400
    user.refresh_from_db()
    assert user.check_password("old-password1")


@pytest.mark.django_db
def test_change_password_rejects_short_new_password():
    user = get_user_model().objects.create_user("user@example.com", password="old-password1")
    client = APIClient()
    client.force_authenticate(user)

    response = client.post(
        "/api/auth/change-password",
        {"current_password": "old-password1", "new_password": "short"},
    )

    assert response.status_code == 400
    user.refresh_from_db()
    assert user.check_password("old-password1")


@pytest.mark.django_db
def test_change_password_requires_authentication():
    client = APIClient()

    response = client.post(
        "/api/auth/change-password",
        {"current_password": "old-password1", "new_password": "new-password1"},
    )

    assert response.status_code == 401
