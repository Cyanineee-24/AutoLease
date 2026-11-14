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
                self.assertContains(response, "Browsing is free. You'll come right back to this page.")

    def test_logged_in_pages_have_no_modal_or_assets(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('home:dashboard'))
        self.assertNotContains(response, 'id="auth-prompt"')
        self.assertNotContains(response, 'auth_prompt.css')
        self.assertNotContains(response, 'auth_prompt.js')


class LoginToSignUpLinkTests(TestCase):
    def test_register_link_carries_next(self):
        response = self.client.get(reverse('login:login') + '?next=/vehicles/1/')
        self.assertContains(
            response,
            f'<a href="{reverse("register:register")}?next=%2Fvehicles%2F1%2F">Create an account</a>',
            html=True,
        )

    def test_register_link_plain_without_next(self):
        response = self.client.get(reverse('login:login'))
        self.assertContains(
            response,
            f'<a href="{reverse("register:register")}">Create an account</a>',
            html=True,
        )

    def test_offsite_next_not_carried(self):
        # LoginView only exposes a safe next to the template.
        response = self.client.get(reverse('login:login') + '?next=https://evil.com/')
        self.assertNotContains(response, 'evil.com')
