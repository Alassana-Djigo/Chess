from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .choices import TimeCategory
from .timecontrol import categorize_time_control


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


class CategorizeTimeControlTests(SimpleTestCase):
    def test_category_boundaries(self):
        cases = [
            (60, 0, TimeCategory.BULLET),
            (179, 0, TimeCategory.BULLET),
            (180, 0, TimeCategory.BLITZ),
            (300, 3, TimeCategory.BLITZ),  # 300 + 40 * 3 = 420
            (479, 0, TimeCategory.BLITZ),
            (480, 0, TimeCategory.RAPID),
            (600, 0, TimeCategory.RAPID),
            (900, 10, TimeCategory.RAPID),  # 900 + 40 * 10 = 1300
            (1499, 0, TimeCategory.RAPID),
            (1500, 0, TimeCategory.CLASSICAL),
            (5400, 1800, TimeCategory.CLASSICAL),
        ]
        for base, increment, expected in cases:
            with self.subTest(base=base, increment=increment):
                self.assertEqual(categorize_time_control(base, increment), expected)

    def test_increment_defaults_to_zero(self):
        self.assertEqual(categorize_time_control(60), TimeCategory.BULLET)

    def test_increment_counts_forty_times(self):
        self.assertEqual(categorize_time_control(120, 0), TimeCategory.BULLET)
        self.assertEqual(categorize_time_control(120, 2), TimeCategory.BLITZ)  # 120 + 80 = 200
