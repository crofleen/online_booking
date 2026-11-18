"""Формы регистрации и входа клиента."""

import re

from django import forms
from django.contrib.auth import get_user_model, password_validation

from apps.booking.models import Client

User = get_user_model()


def normalize_phone(raw):
    """Приводит номер к формату +7XXXXXXXXXX."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    if len(digits) != 11 or not digits.startswith("7"):
        raise forms.ValidationError("Укажите телефон в формате +7XXXXXXXXXX")
    return "+" + digits


class ClientRegistrationForm(forms.Form):
    """Регистрация клиента: учётная запись создаётся по номеру телефона."""

    phone = forms.CharField(label="Телефон", max_length=20,
                            widget=forms.TextInput(attrs={"placeholder": "+7 916 123-45-67",
                                                          "autocomplete": "tel"}))
    last_name = forms.CharField(label="Фамилия", max_length=60)
    first_name = forms.CharField(label="Имя", max_length=60)
    email = forms.EmailField(label="Электронная почта", required=False)
    address = forms.CharField(label="Адрес визита", max_length=250)
    password1 = forms.CharField(label="Пароль", widget=forms.PasswordInput,
                                help_text="Не менее 6 символов")
    password2 = forms.CharField(label="Повторите пароль", widget=forms.PasswordInput)
    consent = forms.BooleanField(label="Согласен на обработку персональных данных")

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        if User.objects.filter(username=phone).exists():
            raise forms.ValidationError("Клиент с таким телефоном уже зарегистрирован")
        return phone

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Пароли не совпадают")
        if password1:
            password_validation.validate_password(password1)
        return cleaned

    def save(self):
        data = self.cleaned_data
        user = User.objects.create_user(username=data["phone"], password=data["password1"],
                                        email=data.get("email", ""))
        Client.objects.update_or_create(
            phone=data["phone"],
            defaults={
                "user": user,
                "last_name": data["last_name"],
                "first_name": data["first_name"],
                "email": data.get("email", ""),
                "address": data["address"],
            },
        )
        return user


class ClientProfileForm(forms.ModelForm):
    """Редактирование контактных данных клиента."""

    class Meta:
        model = Client
        fields = ("last_name", "first_name", "email", "address")
        labels = {
            "last_name": "Фамилия",
            "first_name": "Имя",
            "email": "Электронная почта",
            "address": "Адрес визита",
        }
