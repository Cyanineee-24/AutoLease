from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class AuthPromptModalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='renter@example.com',
            email='renter@example.com',
            password='password123',
            is_renter=True,
        )

    def test_guest_pages_include_modal_once_with_assets(self):
        for url in (reverse('home:landing'), reverse('home:dashboard'), reverse('login:login')):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, '<dialog id="auth-prompt"', count=1)
                self.assertContains(response, f'data-login-url="{reverse("login:login")}"')
                self.assertContains(response, f'data-register-url="{reverse("register:register")}"')
                self.assertContains(response, 'css/login/auth_prompt.css')
                self.assertContains(response, 'js/login/auth_prompt.js')

    def test_logged_in_pages_have_no_modal_or_assets(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('home:dashboard'))
        self.assertNotContains(response, 'id="auth-prompt"')
        self.assertNotContains(response, 'auth_prompt.css')
        self.assertNotContains(response, 'auth_prompt.js')
