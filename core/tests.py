from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AdminSmokeTests(TestCase):
    """Rede de seguranca: todas as paginas do admin abrem e a pesquisa nao rebenta.

    Apanha erros de configuracao (search_fields, list_filter...) em qualquer model novo.
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin_user = get_user_model().objects.create_superuser(
            "admin", "admin@example.com", "pw"
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_changelist_search_and_add_pages_load(self):
        for model, model_admin in admin.site._registry.items():
            meta = model._meta
            prefix = f"admin:{meta.app_label}_{meta.model_name}"
            with self.subTest(model=meta.label):
                changelist = reverse(f"{prefix}_changelist")
                self.assertEqual(self.client.get(changelist).status_code, 200)
                if model_admin.search_fields:
                    response = self.client.get(changelist, {"q": "carlsen"})
                    self.assertEqual(response.status_code, 200)
                self.assertEqual(self.client.get(reverse(f"{prefix}_add")).status_code, 200)
