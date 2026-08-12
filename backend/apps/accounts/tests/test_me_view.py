import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_me_returns_is_staff_true_for_staff_user():
    user = get_user_model().objects.create_user(
        "staff@example.com", password="secure-pass", is_staff=True
    )
    client = APIClient()
    client.force_authenticate(user)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {"is_staff": True}


@pytest.mark.django_db
def test_me_returns_is_staff_false_for_regular_user():
    user = get_user_model().objects.create_user("regular@example.com", password="secure-pass")
    client = APIClient()
    client.force_authenticate(user)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {"is_staff": False}


@pytest.mark.django_db
def test_me_requires_authentication():
    client = APIClient()

    response = client.get("/api/auth/me")

    assert response.status_code == 401
