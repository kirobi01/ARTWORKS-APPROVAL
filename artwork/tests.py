import io
from django.test import TestCase, Client, override_settings
from django.core.mail import EmailMessage
from unittest.mock import patch
from django.contrib.auth.models import User, Group
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from artwork.models import ArtworkRequest, LogoTemplate, ArtworkLogoCheck
from artwork.services import ArtworkStatusManager
from artwork.utils import generate_artwork_number
from artwork.views import _save_logo_checks_from_post, _get_logo_form_state, _ensure_logo_templates


class ArtworkWorkflowTests(TestCase):
    def setUp(self):
        self.designer = User.objects.create_user('designer', password='pass')
        self.marketer = User.objects.create_user('marketer', password='pass')
        Group.objects.get_or_create(name='DESIGN')
        Group.objects.get_or_create(name='MARKETING_SALES')
        self.designer.groups.add(Group.objects.get(name='DESIGN'))
        self.marketer.groups.add(Group.objects.get(name='MARKETING_SALES'))

    def test_generate_artwork_number(self):
        num = generate_artwork_number()
        self.assertTrue(num.startswith('ART-'))

    def test_submit_and_approve_flow(self):
        artwork = ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='Classic Lavender',
            sku_size='500gm Wrapper',
            created_by=self.designer,
            status='Design Created',
        )
        ArtworkStatusManager.submit_for_approval(artwork, self.designer)
        artwork.refresh_from_db()
        self.assertEqual(artwork.status, 'Pending: Marketing & Sales Approval')

        ArtworkStatusManager.approve(artwork, 'marketing', self.marketer, 'Looks good')
        artwork.refresh_from_db()
        self.assertTrue(artwork.marketing_approved)
        self.assertEqual(artwork.status, 'Pending: Quality Assurance Approval')

    def test_rejection_resets_to_design_revision(self):
        artwork = ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='Test Product',
            created_by=self.designer,
            status='Pending: Marketing & Sales Approval',
        )
        ArtworkStatusManager.reject(artwork, 'marketing', self.marketer, 'Fix barcode')
        artwork.refresh_from_db()
        self.assertEqual(artwork.status, 'Pending: Design Revision')
        self.assertEqual(artwork.revision_count, 1)
        self.assertTrue(artwork.is_rejected)
        self.assertEqual(artwork.current_user, self.designer)


class ArtworkViewTests(TestCase):
    def test_login_page_loads(self):
        client = Client()
        response = client.get('/artwork/login/')
        self.assertEqual(response.status_code, 200)


def _test_png_file(name='kapa.png'):
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), color=(204, 28, 36)).save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


class LogoTemplateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('designer', password='pass')
        Group.objects.get_or_create(name='DESIGN')
        self.user.groups.add(Group.objects.get(name='DESIGN'))
        self.client = Client()
        self.client.login(username='designer', password='pass')

        self.png = _test_png_file()
        self.template = LogoTemplate.objects.create(
            name='Kapa Test',
            icon=self.png,
            display_order=1,
            is_active=True,
        )

    def test_logo_icon_view_requires_auth(self):
        client = Client()
        response = client.get(f'/artwork/logo-icons/{self.template.id}/')
        self.assertEqual(response.status_code, 302)

    def test_logo_icon_view_serves_image(self):
        response = self.client.get(f'/artwork/logo-icons/{self.template.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('image/'))

    def test_save_logo_checks_by_template_id(self):
        artwork = ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='Test',
            created_by=self.user,
            status='Design Created',
        )
        post_data = {
            f'logo_status_{self.template.id}': 'Okay',
            f'logo_colors_{self.template.id}': 'Pantone 273 C',
        }
        _save_logo_checks_from_post(artwork, post_data)
        check = ArtworkLogoCheck.objects.get(artwork_request=artwork, logo_name='Kapa Test')
        self.assertEqual(check.status, 'Okay')
        self.assertEqual(check.colors_used, 'Pantone 273 C')
        self.assertEqual(check.logo_template_id, self.template.id)

    def test_logo_form_state_from_post(self):
        templates = _ensure_logo_templates()
        state = _get_logo_form_state(
            templates,
            post_data={f'logo_status_{self.template.id}': 'N/A'},
        )
        self.assertEqual(state[self.template.id]['status'], 'N/A')

    def test_create_page_shows_logo_picker(self):
        response = self.client.get('/artwork/create/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'logoPicker')
        self.assertContains(response, 'logo_status_')

    def test_logo_library_page_for_designer(self):
        response = self.client.get('/artwork/logos/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Logo Library')
        self.assertContains(response, 'Save Logo')

    def test_logo_library_create_via_post(self):
        response = self.client.post('/artwork/logos/', {
            'name': 'New Halal Logo',
            'icon': _test_png_file('new-halal.png'),
        })
        self.assertEqual(response.status_code, 302)
        logo = LogoTemplate.objects.get(name='New Halal Logo')
        self.assertTrue(logo.is_active)

    def test_logo_library_requires_design_group(self):
        other = User.objects.create_user('viewer', password='pass')
        self.client.login(username='viewer', password='pass')
        response = self.client.get('/artwork/logos/')
        self.assertEqual(response.status_code, 403)


@override_settings(
    EMAIL_BACKEND='config.email_backends.DevelopmentRedirectEmailBackend',
    DEV_EMAIL_OVERRIDE='support.user5@kapa-oil.com',
    EMAIL_HOST='localhost',
    EMAIL_PORT=25,
)
class DevelopmentEmailTests(TestCase):
    def test_dev_backend_redirects_all_recipients(self):
        from config.email_backends import DevelopmentRedirectEmailBackend
        from django.core.mail.backends.smtp import EmailBackend as SMTPBackend

        backend = DevelopmentRedirectEmailBackend()
        msg = EmailMessage(
            subject='Artwork alert',
            body='Test body',
            from_email='noreply@example.com',
            to=['marketing@kapa-oil.com'],
            cc=['admin@kapa-oil.com'],
        )

        with patch.object(SMTPBackend, 'send_messages', return_value=1) as mock_send:
            backend.send_messages([msg])
            sent = mock_send.call_args[0][0][0]

        self.assertEqual(sent.to, ['support.user5@kapa-oil.com'])
        self.assertEqual(sent.cc, [])
        self.assertTrue(sent.subject.startswith('[DEV]'))
        self.assertIn('marketing@kapa-oil.com', sent.body)
