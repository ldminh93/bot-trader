from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "email", "password")

    def create(self, validated_data):
        email = validated_data["email"].lower().strip()
        return User.objects.create_user(
            username=email,
            email=email,
            password=validated_data["password"],
        )

