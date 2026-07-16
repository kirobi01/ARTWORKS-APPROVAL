import io
from django.test import TestCase, Client, override_settings
from django.core.mail import EmailMessage
from unittest.mock import patch
from django.contrib.auth.models import User, Group
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from artwork.models import ArtworkRequest, LogoTemplate, ArtworkLogoCheck, ProductCategory
from artwork.services import ArtworkStatusManager, ArtworkNotificationService
from artwork.operations_routing import (
    user_can_approve_operations,
    filter_operations_pending_queryset,
    get_operations_assignees,
)
from artwork.utils import generate_artwork_number
from artwork.views import (
    _save_logo_checks_from_post,
    _get_logo_form_state,
    _ensure_logo_templates,
    _can_view,
    _can_review,
    _can_fill_procurement,
    _can_download_pdf,
    _artworks_for_user,
)


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


class ArtworkDraftSaveTests(TestCase):
    def setUp(self):
        self.designer = User.objects.create_user('draft_designer', password='pass')
        Group.objects.get_or_create(name='DESIGN')
        self.designer.groups.add(Group.objects.get(name='DESIGN'))
        self.client = Client()
        self.client.force_login(self.designer)

    def test_save_empty_draft_succeeds(self):
        get_page = self.client.get('/artwork/create/')
        artwork_no = get_page.context['artwork_no']
        response = self.client.post('/artwork/create/', {
            'action': 'save',
            'artwork_no': artwork_no,
        })
        self.assertEqual(response.status_code, 302)
        draft = ArtworkRequest.objects.get(created_by=self.designer)
        self.assertEqual(draft.status, 'Draft')
        self.assertEqual(draft.product_name, '')
        self.assertEqual(draft.artwork_no, artwork_no)
        self.assertIn('/artwork/edit/', response.url)

    def test_save_draft_with_fields_persists(self):
        response = self.client.post('/artwork/create/', {
            'action': 'save',
            'product_name': 'Draft Soap',
            'sku_size': '250ml',
            'barcode': '4006381333931',
            'ingredients': 'Water, oil',
        })
        self.assertEqual(response.status_code, 302)
        draft = ArtworkRequest.objects.get(created_by=self.designer)
        self.assertEqual(draft.status, 'Draft')
        self.assertEqual(draft.product_name, 'Draft Soap')
        self.assertEqual(draft.sku_size, '250ml')
        self.assertEqual(draft.barcode, '4006381333931')
        self.assertEqual(draft.ingredients, 'Water, oil')

    def test_update_draft_persists_changes(self):
        artwork = ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='Old Name',
            created_by=self.designer,
            status='Draft',
        )
        response = self.client.post(f'/artwork/edit/{artwork.artwork_no}/', {
            'action': 'save',
            'product_name': 'Updated Draft',
            'sku_size': '1kg',
        })
        self.assertEqual(response.status_code, 302)
        artwork.refresh_from_db()
        self.assertEqual(artwork.status, 'Draft')
        self.assertEqual(artwork.product_name, 'Updated Draft')
        self.assertEqual(artwork.sku_size, '1kg')

    def test_drafts_list_shows_saved_draft(self):
        ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='Listed Draft',
            created_by=self.designer,
            status='Draft',
        )
        response = self.client.get('/artwork/drafts/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Listed Draft')

    def test_submit_without_product_name_fails_cleanly(self):
        response = self.client.post('/artwork/create/', {'action': 'submit'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ArtworkRequest.objects.filter(created_by=self.designer).exists())
        self.assertContains(response, 'Product name is required')

    def test_submit_without_category_fails_cleanly(self):
        response = self.client.post('/artwork/create/', {
            'action': 'submit',
            'product_name': 'Needs Category',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ArtworkRequest.objects.filter(created_by=self.designer).exists())
        self.assertContains(response, 'Product category is required')

    def test_invalid_barcode_rejected_on_draft(self):
        response = self.client.post('/artwork/create/', {
            'action': 'save',
            'product_name': 'Bad Barcode',
            'barcode': '123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ArtworkRequest.objects.filter(created_by=self.designer).exists())
        self.assertContains(response, 'barcode length')

    def test_valid_ean13_barcode_accepted(self):
        # Well-known valid EAN-13 (Wikipedia example)
        response = self.client.post('/artwork/create/', {
            'action': 'save',
            'product_name': 'Good Barcode',
            'barcode': '4006381333931',
        })
        self.assertEqual(response.status_code, 302)
        draft = ArtworkRequest.objects.get(created_by=self.designer)
        self.assertEqual(draft.barcode, '4006381333931')


class DesignTeamCollaborationTests(TestCase):
    def setUp(self):
        Group.objects.get_or_create(name='DESIGN')
        Group.objects.get_or_create(name='MARKETING_SALES')
        design = Group.objects.get(name='DESIGN')
        self.designer_a = User.objects.create_user('designer_a', password='pass')
        self.designer_b = User.objects.create_user('designer_b', password='pass')
        self.marketer = User.objects.create_user('marketer', password='pass')
        self.designer_a.groups.add(design)
        self.designer_b.groups.add(design)
        self.marketer.groups.add(Group.objects.get(name='MARKETING_SALES'))
        self.teammate_draft = ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='Teammate Draft',
            created_by=self.designer_a,
            status='Draft',
        )
        self.client = Client()

    def test_designer_sees_teammate_drafts(self):
        self.client.force_login(self.designer_b)
        response = self.client.get('/artwork/drafts/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Teammate Draft')
        self.assertContains(response, 'Continue')

    def test_designer_can_edit_teammate_draft(self):
        self.client.force_login(self.designer_b)
        response = self.client.post(
            f'/artwork/edit/{self.teammate_draft.artwork_no}/',
            {'action': 'save', 'product_name': 'Updated By Teammate'},
        )
        self.assertEqual(response.status_code, 302)
        self.teammate_draft.refresh_from_db()
        self.assertEqual(self.teammate_draft.product_name, 'Updated By Teammate')
        self.assertEqual(self.teammate_draft.created_by, self.designer_a)

    def test_designer_can_view_teammate_draft_detail(self):
        self.client.force_login(self.designer_b)
        response = self.client.get(
            f'/artwork/{self.teammate_draft.artwork_no}/detail/'
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_edit'])
        self.assertContains(response, 'Continue Draft')

    def test_marketer_cannot_create_or_edit_draft(self):
        self.client.force_login(self.marketer)
        self.assertEqual(self.client.get('/artwork/create/').status_code, 403)
        self.assertEqual(
            self.client.get(
                f'/artwork/edit/{self.teammate_draft.artwork_no}/'
            ).status_code,
            403,
        )

    def test_pending_excludes_drafts_for_design(self):
        self.client.force_login(self.designer_b)
        response = self.client.get('/artwork/pending/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Teammate Draft')

    def test_design_revision_lives_on_drafts_not_pending(self):
        revision = ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='Needs Revision',
            created_by=self.designer_a,
            status='Pending: Design Revision',
        )
        self.client.force_login(self.designer_b)
        drafts = self.client.get('/artwork/drafts/')
        self.assertEqual(drafts.status_code, 200)
        self.assertContains(drafts, 'Needs Revision')
        self.assertContains(drafts, 'Edit')
        pending = self.client.get('/artwork/pending/')
        self.assertEqual(pending.status_code, 200)
        self.assertNotContains(pending, 'Needs Revision')
        # Designer can still open and edit the revision
        detail = self.client.get(f'/artwork/{revision.artwork_no}/detail/')
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.context['can_edit'])
        self.assertEqual(
            self.client.get(f'/artwork/edit/{revision.artwork_no}/').status_code,
            200,
        )

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
        self.client.force_login(self.user)

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

    def test_create_page_shows_reserved_artwork_number(self):
        response = self.client.get('/artwork/create/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Artwork No')
        self.assertRegex(response.content.decode(), r'ART-\d{4}-\d{4}')
        self.assertContains(response, 'name="artwork_no"')

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


class OperationsCategoryRoutingTests(TestCase):
    def setUp(self):
        Group.objects.get_or_create(name='OPERATIONS_HOD')
        Group.objects.get_or_create(name='DESIGN')
        ops = Group.objects.get(name='OPERATIONS_HOD')

        self.designer = User.objects.create_user('ops_designer', password='pass')
        self.designer.groups.add(Group.objects.get(name='DESIGN'))

        self.oils_hod = User.objects.create_user(
            'oils_hod', password='pass', email='oils.hod@example.com',
        )
        self.oils_deputy = User.objects.create_user(
            'oils_deputy', password='pass', email='oils.deputy@example.com',
        )
        self.soap_hod = User.objects.create_user(
            'soap_hod', password='pass', email='soap.hod@example.com',
        )
        self.other_ops = User.objects.create_user(
            'other_ops', password='pass', email='other.ops@example.com',
        )
        for u in (self.oils_hod, self.oils_deputy, self.soap_hod, self.other_ops):
            u.groups.add(ops)

        self.oils = ProductCategory.objects.create(
            name='Edible Oils', hod=self.oils_hod, deputy_hod=self.oils_deputy,
        )
        self.soap = ProductCategory.objects.create(
            name='Soap', hod=self.soap_hod,
        )

        self.oils_artwork = ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='Classic Oil',
            product_category='Edible Oils',
            created_by=self.designer,
            status='Pending: Operations HOD Approval',
        )
        self.soap_artwork = ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='Bar Soap',
            product_category='Soap',
            created_by=self.designer,
            status='Pending: Operations HOD Approval',
        )
        self.unmapped_artwork = ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='Mystery Item',
            product_category='Tissue',
            created_by=self.designer,
            status='Pending: Operations HOD Approval',
        )

    def test_assignees_include_hod_and_deputy(self):
        assignees = get_operations_assignees(self.oils_artwork)
        self.assertEqual(
            {u.username for u in assignees},
            {'oils_hod', 'oils_deputy'},
        )

    def test_only_mapped_users_can_approve(self):
        self.assertTrue(user_can_approve_operations(self.oils_hod, self.oils_artwork))
        self.assertTrue(user_can_approve_operations(self.oils_deputy, self.oils_artwork))
        self.assertFalse(user_can_approve_operations(self.soap_hod, self.oils_artwork))
        self.assertFalse(user_can_approve_operations(self.other_ops, self.oils_artwork))

    def test_unmapped_category_allows_any_ops_hod(self):
        self.assertTrue(user_can_approve_operations(self.other_ops, self.unmapped_artwork))
        self.assertTrue(user_can_approve_operations(self.oils_hod, self.unmapped_artwork))

    def test_pending_list_filtered_by_department(self):
        qs = ArtworkRequest.objects.filter(status='Pending: Operations HOD Approval')
        oils_pending = filter_operations_pending_queryset(qs, self.oils_hod)
        soap_pending = filter_operations_pending_queryset(qs, self.soap_hod)

        oils_nos = set(oils_pending.values_list('artwork_no', flat=True))
        soap_nos = set(soap_pending.values_list('artwork_no', flat=True))

        self.assertIn(self.oils_artwork.artwork_no, oils_nos)
        self.assertNotIn(self.soap_artwork.artwork_no, oils_nos)
        self.assertIn(self.unmapped_artwork.artwork_no, oils_nos)

        self.assertIn(self.soap_artwork.artwork_no, soap_nos)
        self.assertNotIn(self.oils_artwork.artwork_no, soap_nos)

    def test_operations_approval_forbidden_for_other_department(self):
        client = Client()
        client.force_login(self.soap_hod)
        response = client.get(f'/artwork/{self.oils_artwork.artwork_no}/operations-approval/')
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'Wrong department', status_code=403)
        self.assertContains(response, 'another department', status_code=403)
        self.assertContains(response, 'Go to Pending', status_code=403)

    def test_operations_approval_allowed_for_mapped_hod(self):
        client = Client()
        client.force_login(self.oils_hod)
        response = client.get(f'/artwork/{self.oils_artwork.artwork_no}/operations-approval/')
        self.assertEqual(response.status_code, 200)

    def test_operations_approval_allowed_for_deputy(self):
        client = Client()
        client.force_login(self.oils_deputy)
        response = client.get(f'/artwork/{self.oils_artwork.artwork_no}/operations-approval/')
        self.assertEqual(response.status_code, 200)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_ops_alert_goes_to_category_assignees_only(self):
        from django.core import mail

        ArtworkNotificationService.send_approval_notification(
            self.oils_artwork, 'qa', 'operations_hod', actor=self.designer,
        )
        self.assertEqual(len(mail.outbox), 1)
        recipients = set(mail.outbox[0].to)
        self.assertIn('oils.hod@example.com', recipients)
        self.assertIn('oils.deputy@example.com', recipients)
        self.assertNotIn('soap.hod@example.com', recipients)
        self.assertNotIn('other.ops@example.com', recipients)

    def test_deputy_can_approve_and_advance(self):
        ArtworkStatusManager.approve(
            self.oils_artwork, 'operations_hod', self.oils_deputy, 'OK from deputy',
        )
        self.oils_artwork.refresh_from_db()
        self.assertTrue(self.oils_artwork.operations_hod_approved)
        self.assertEqual(self.oils_artwork.operations_hod_by, self.oils_deputy)
        self.assertEqual(self.oils_artwork.status, 'Pending: Product Development Approval')

    def test_service_blocks_cross_department_approve(self):
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            ArtworkStatusManager.approve(
                self.oils_artwork, 'operations_hod', self.soap_hod, 'Should fail',
            )
        self.oils_artwork.refresh_from_db()
        self.assertFalse(self.oils_artwork.operations_hod_approved)
        self.assertEqual(self.oils_artwork.status, 'Pending: Operations HOD Approval')

    def test_service_blocks_cross_department_reject(self):
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            ArtworkStatusManager.reject(
                self.oils_artwork, 'operations_hod', self.other_ops, 'Should fail',
            )
        self.oils_artwork.refresh_from_db()
        self.assertFalse(self.oils_artwork.operations_hod_rejected)
        self.assertEqual(self.oils_artwork.status, 'Pending: Operations HOD Approval')

    def test_post_approve_blocked_for_other_department(self):
        client = Client()
        client.force_login(self.soap_hod)
        response = client.post(
            f'/artwork/{self.oils_artwork.artwork_no}/operations-approval/',
            {'action': 'approved', 'comments': 'Trying to approve oils'},
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn('department', data.get('message', '').lower())
        self.oils_artwork.refresh_from_db()
        self.assertFalse(self.oils_artwork.operations_hod_approved)
        self.assertEqual(self.oils_artwork.status, 'Pending: Operations HOD Approval')

    def test_post_reject_blocked_for_other_department(self):
        client = Client()
        client.force_login(self.other_ops)
        response = client.post(
            f'/artwork/{self.oils_artwork.artwork_no}/operations-approval/',
            {'action': 'rejected', 'comments': 'Trying to reject oils'},
        )
        self.assertEqual(response.status_code, 403)
        self.oils_artwork.refresh_from_db()
        self.assertFalse(self.oils_artwork.is_rejected)
        self.assertEqual(self.oils_artwork.status, 'Pending: Operations HOD Approval')

    def test_inactive_category_stays_locked_to_mapped_department(self):
        self.oils.is_active = False
        self.oils.save(update_fields=['is_active'])
        self.assertFalse(user_can_approve_operations(self.soap_hod, self.oils_artwork))
        self.assertTrue(user_can_approve_operations(self.oils_hod, self.oils_artwork))
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            ArtworkStatusManager.approve(
                self.oils_artwork, 'operations_hod', self.soap_hod, 'No',
            )

    def test_inactive_mapped_hod_does_not_open_to_other_departments(self):
        self.oils_hod.is_active = False
        self.oils_hod.save()
        self.oils_deputy.is_active = False
        self.oils_deputy.save()
        # Mapping still exists → other ops HODs must not gain access
        self.assertFalse(user_can_approve_operations(self.soap_hod, self.oils_artwork))
        self.assertFalse(user_can_approve_operations(self.other_ops, self.oils_artwork))
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            ArtworkStatusManager.approve(
                self.oils_artwork, 'operations_hod', self.soap_hod, 'No',
            )

    def test_end_to_end_only_mapped_hod_advances_workflow(self):
        # Wrong department blocked
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            ArtworkStatusManager.approve(
                self.oils_artwork, 'operations_hod', self.soap_hod, 'No',
            )
        # Correct department advances
        ArtworkStatusManager.approve(
            self.oils_artwork, 'operations_hod', self.oils_hod, 'Oils OK',
        )
        self.oils_artwork.refresh_from_db()
        self.assertEqual(self.oils_artwork.status, 'Pending: Product Development Approval')
        self.assertEqual(self.oils_artwork.operations_hod_by, self.oils_hod)


STAGE_CASES = [
    {
        'key': 'marketing',
        'group': 'MARKETING_SALES',
        'status': 'Pending: Marketing & Sales Approval',
        'url': 'marketing-approval',
        'approved_flag': 'marketing_approved',
        'by_field': 'marketing_by',
        'next_status': 'Pending: Quality Assurance Approval',
    },
    {
        'key': 'qa',
        'group': 'QUALITY_ASSURANCE',
        'status': 'Pending: Quality Assurance Approval',
        'url': 'qa-approval',
        'approved_flag': 'qa_approved',
        'by_field': 'qa_by',
        'next_status': 'Pending: Operations HOD Approval',
    },
    {
        'key': 'operations_hod',
        'group': 'OPERATIONS_HOD',
        'status': 'Pending: Operations HOD Approval',
        'url': 'operations-approval',
        'approved_flag': 'operations_hod_approved',
        'by_field': 'operations_hod_by',
        'next_status': 'Pending: Product Development Approval',
    },
    {
        'key': 'product_dev',
        'group': 'PRODUCT_DEVELOPMENT',
        'status': 'Pending: Product Development Approval',
        'url': 'product-dev-approval',
        'approved_flag': 'product_dev_approved',
        'by_field': 'product_dev_by',
        'next_status': 'Pending: Milan Shah Approval',
    },
    {
        'key': 'milan',
        'group': 'MILAN',
        'status': 'Pending: Milan Shah Approval',
        'url': 'milan-approval',
        'approved_flag': 'milan_approved',
        'by_field': 'milan_by',
        'next_status': 'Completed / Approved',
    },
]


class AllApprovalStagesTests(TestCase):
    """Permission and workflow coverage for every approval stage."""

    def setUp(self):
        self.designer = User.objects.create_user(
            'stage_designer', password='pass', email='designer@example.com',
        )
        Group.objects.get_or_create(name='DESIGN')
        self.designer.groups.add(Group.objects.get(name='DESIGN'))

        self.users = {}
        for case in STAGE_CASES:
            Group.objects.get_or_create(name=case['group'])
            user = User.objects.create_user(
                f"user_{case['key']}",
                password='pass',
                email=f"{case['key']}@example.com",
            )
            user.groups.add(Group.objects.get(name=case['group']))
            self.users[case['key']] = user

        # Outsider with no approval groups
        self.outsider = User.objects.create_user('outsider', password='pass')

    def _artwork_at(self, status, category='Edible Oils'):
        return ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='Stage Test Product',
            product_category=category,
            sku_size='1L',
            created_by=self.designer,
            status=status,
        )

    def test_full_pipeline_all_stages_to_completed(self):
        artwork = self._artwork_at('Design Created')
        ArtworkStatusManager.submit_for_approval(artwork, self.designer)
        artwork.refresh_from_db()
        self.assertEqual(artwork.status, 'Pending: Marketing & Sales Approval')

        for case in STAGE_CASES:
            ArtworkStatusManager.approve(
                artwork, case['key'], self.users[case['key']], f"OK {case['key']}",
            )
            artwork.refresh_from_db()
            self.assertTrue(getattr(artwork, case['approved_flag']))
            self.assertEqual(getattr(artwork, case['by_field']), self.users[case['key']])
            self.assertEqual(artwork.status, case['next_status'])

        self.assertEqual(artwork.status, 'Completed / Approved')
        self.assertFalse(artwork.is_rejected)

    def test_each_stage_page_allows_correct_group(self):
        for case in STAGE_CASES:
            artwork = self._artwork_at(case['status'])
            client = Client()
            client.force_login(self.users[case['key']])
            response = client.get(f"/artwork/{artwork.artwork_no}/{case['url']}/")
            self.assertEqual(
                response.status_code, 200,
                msg=f"{case['key']} should access their approval page",
            )

    def test_each_stage_page_forbids_wrong_groups(self):
        for case in STAGE_CASES:
            artwork = self._artwork_at(case['status'])
            for other in STAGE_CASES:
                if other['key'] == case['key']:
                    continue
                client = Client()
                client.force_login(self.users[other['key']])
                response = client.get(f"/artwork/{artwork.artwork_no}/{case['url']}/")
                self.assertEqual(
                    response.status_code, 403,
                    msg=f"{other['key']} must not open {case['key']} approval",
                )

    def test_outsider_cannot_open_any_stage(self):
        for case in STAGE_CASES:
            artwork = self._artwork_at(case['status'])
            client = Client()
            client.force_login(self.outsider)
            response = client.get(f"/artwork/{artwork.artwork_no}/{case['url']}/")
            self.assertEqual(response.status_code, 403)

    def test_each_stage_post_approve_succeeds_for_correct_user(self):
        for case in STAGE_CASES:
            artwork = self._artwork_at(case['status'])
            client = Client()
            client.force_login(self.users[case['key']])
            response = client.post(
                f"/artwork/{artwork.artwork_no}/{case['url']}/",
                {'action': 'approved', 'comments': f"Approved at {case['key']}"},
            )
            self.assertEqual(response.status_code, 200, msg=case['key'])
            data = response.json()
            self.assertTrue(data.get('success'), msg=case['key'])
            artwork.refresh_from_db()
            self.assertTrue(getattr(artwork, case['approved_flag']))
            self.assertEqual(artwork.status, case['next_status'])

    def test_each_stage_post_approve_forbidden_for_wrong_user(self):
        for case in STAGE_CASES:
            artwork = self._artwork_at(case['status'])
            # Pick a different stage user
            wrong_key = 'qa' if case['key'] != 'qa' else 'marketing'
            client = Client()
            client.force_login(self.users[wrong_key])
            response = client.post(
                f"/artwork/{artwork.artwork_no}/{case['url']}/",
                {'action': 'approved', 'comments': 'Cross-stage attempt'},
            )
            self.assertEqual(response.status_code, 403, msg=f"{wrong_key} -> {case['key']}")
            artwork.refresh_from_db()
            self.assertFalse(getattr(artwork, case['approved_flag']))
            self.assertEqual(artwork.status, case['status'])

    def test_each_stage_reject_returns_to_design_revision(self):
        for case in STAGE_CASES:
            artwork = self._artwork_at(case['status'])
            ArtworkStatusManager.reject(
                artwork, case['key'], self.users[case['key']], f"Reject {case['key']}",
            )
            artwork.refresh_from_db()
            self.assertEqual(artwork.status, 'Pending: Design Revision')
            self.assertTrue(artwork.is_rejected)
            self.assertEqual(artwork.revision_count, 1)
            self.assertEqual(artwork.current_user, self.designer)
            self.assertTrue(artwork.rejection_stage)
            self.assertEqual(artwork.rejection_comments, f"Reject {case['key']}")

    def test_each_stage_post_reject_succeeds_for_correct_user(self):
        for case in STAGE_CASES:
            artwork = self._artwork_at(case['status'])
            client = Client()
            client.force_login(self.users[case['key']])
            response = client.post(
                f"/artwork/{artwork.artwork_no}/{case['url']}/",
                {'action': 'rejected', 'comments': f"Reject at {case['key']}"},
            )
            self.assertEqual(response.status_code, 200, msg=case['key'])
            self.assertTrue(response.json().get('success'))
            artwork.refresh_from_db()
            self.assertEqual(artwork.status, 'Pending: Design Revision')
            self.assertTrue(artwork.is_rejected)

    def test_wrong_status_cannot_be_approved_via_service(self):
        from django.core.exceptions import PermissionDenied
        artwork = self._artwork_at('Pending: Marketing & Sales Approval')
        # QA user/stage against marketing-status artwork
        with self.assertRaises(PermissionDenied):
            ArtworkStatusManager.approve(
                artwork, 'qa', self.users['qa'], 'Wrong stage',
            )
        artwork.refresh_from_db()
        self.assertEqual(artwork.status, 'Pending: Marketing & Sales Approval')
        self.assertFalse(artwork.qa_approved)

    def test_wrong_status_page_redirects_without_acting(self):
        artwork = self._artwork_at('Pending: Marketing & Sales Approval')
        client = Client()
        client.force_login(self.users['qa'])
        # QA user opening QA URL while artwork is still at marketing
        response = client.get(f'/artwork/{artwork.artwork_no}/qa-approval/')
        self.assertEqual(response.status_code, 302)
        artwork.refresh_from_db()
        self.assertEqual(artwork.status, 'Pending: Marketing & Sales Approval')

    def test_resubmit_after_rejection_restarts_at_marketing(self):
        artwork = self._artwork_at('Pending: Quality Assurance Approval')
        ArtworkStatusManager.reject(artwork, 'qa', self.users['qa'], 'Fix colors')
        artwork.refresh_from_db()
        self.assertEqual(artwork.status, 'Pending: Design Revision')

        ArtworkStatusManager.reset_approval_flags(artwork)
        ArtworkStatusManager.submit_for_approval(artwork, self.designer)
        artwork.refresh_from_db()
        self.assertEqual(artwork.status, 'Pending: Marketing & Sales Approval')
        self.assertFalse(artwork.marketing_approved)
        self.assertFalse(artwork.qa_approved)
        self.assertFalse(artwork.is_rejected)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_each_stage_advance_notifies_next_stage_group(self):
        from django.core import mail

        artwork = self._artwork_at('Pending: Marketing & Sales Approval')
        mail.outbox.clear()
        ArtworkStatusManager.approve(
            artwork, 'marketing', self.users['marketing'], 'To QA',
        )
        self.assertGreaterEqual(len(mail.outbox), 1)
        # Next stage is QA — recipient list should include QA email when present
        recipients = set()
        for msg in mail.outbox:
            recipients.update(msg.to)
        self.assertIn('qa@example.com', recipients)


class AccessControlAuditTests(TestCase):
    """Backend/frontend ACL parity: pages, list actions, and artwork visibility."""

    def setUp(self):
        for name in (
            'DESIGN', 'MARKETING_SALES', 'QUALITY_ASSURANCE', 'OPERATIONS_HOD',
            'PRODUCT_DEVELOPMENT', 'MILAN', 'PROCUREMENT', 'ADMIN',
        ):
            Group.objects.get_or_create(name=name)

        self.designer = User.objects.create_user('acl_designer', password='pass')
        self.marketer = User.objects.create_user('acl_marketer', password='pass')
        self.qa = User.objects.create_user('acl_qa', password='pass')
        self.procurement = User.objects.create_user('acl_procurement', password='pass')
        self.outsider = User.objects.create_user('acl_outsider', password='pass')

        self.designer.groups.add(Group.objects.get(name='DESIGN'))
        self.marketer.groups.add(Group.objects.get(name='MARKETING_SALES'))
        self.qa.groups.add(Group.objects.get(name='QUALITY_ASSURANCE'))
        self.procurement.groups.add(Group.objects.get(name='PROCUREMENT'))

        self.marketing_pending = ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='ACL Marketing Item',
            created_by=self.designer,
            status='Pending: Marketing & Sales Approval',
        )
        self.completed = ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='ACL Completed Item',
            created_by=self.designer,
            status='Completed / Approved',
        )
        self.other_completed = ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='ACL Other Completed',
            created_by=self.marketer,
            status='Completed / Approved',
        )
        self.client = Client()

    def test_creator_cannot_review_own_pending_stage(self):
        self.assertFalse(_can_review(self.marketing_pending, self.designer))
        self.assertTrue(_can_review(self.marketing_pending, self.marketer))
        self.assertFalse(_can_review(self.marketing_pending, self.qa))

    def test_my_artworks_hides_review_for_creator(self):
        self.client.force_login(self.designer)
        response = self.client.get('/artwork/my/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ACL Marketing Item')
        self.assertNotContains(response, f"/artwork/{self.marketing_pending.artwork_no}/marketing-approval/")
        self.assertNotContains(response, '>Review<')

    def test_pending_shows_review_only_for_stage_group(self):
        self.client.force_login(self.marketer)
        response = self.client.get('/artwork/pending/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Review')
        self.assertContains(
            response,
            f"/artwork/{self.marketing_pending.artwork_no}/marketing-approval/",
        )

        self.client.force_login(self.qa)
        response = self.client.get('/artwork/pending/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'ACL Marketing Item')

    def test_detail_hides_sap_link_for_non_procurement(self):
        self.assertFalse(_can_fill_procurement(self.completed, self.designer))
        self.assertTrue(_can_fill_procurement(self.completed, self.procurement))

        self.client.force_login(self.designer)
        response = self.client.get(f'/artwork/{self.completed.artwork_no}/detail/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_fill_procurement'])
        self.assertNotContains(response, 'SAP Details')

        self.client.force_login(self.procurement)
        response = self.client.get(f'/artwork/{self.completed.artwork_no}/detail/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_fill_procurement'])
        self.assertContains(response, 'Add SAP Details')

    def test_procurement_page_requires_group(self):
        self.client.force_login(self.designer)
        self.assertEqual(
            self.client.get(f'/artwork/{self.completed.artwork_no}/procurement/').status_code,
            403,
        )
        self.client.force_login(self.procurement)
        self.assertEqual(
            self.client.get(f'/artwork/{self.completed.artwork_no}/procurement/').status_code,
            200,
        )

    def test_dashboard_counts_respect_visibility(self):
        self.client.force_login(self.marketer)
        response = self.client.get('/artwork/dashboard/')
        self.assertEqual(response.status_code, 200)
        # Marketer only sees own completed (+ pending marketing), not designer's completed.
        visible = _artworks_for_user(self.marketer)
        self.assertEqual(response.context['total_count'], visible.count())
        self.assertEqual(
            response.context['completed_count'],
            visible.filter(status='Completed / Approved').count(),
        )
        self.assertEqual(response.context['completed_count'], 1)
        self.assertNotEqual(
            response.context['completed_count'],
            ArtworkRequest.objects.filter(status='Completed / Approved').count(),
        )

    def test_status_filter_options_do_not_leak_hidden_statuses(self):
        self.client.force_login(self.marketer)
        response = self.client.get('/artwork/all/')
        self.assertEqual(response.status_code, 200)
        statuses = set(response.context['statuses'])
        self.assertIn('Pending: Marketing & Sales Approval', statuses)
        # Marketer did not create the designer draft statuses; completed only own.
        self.assertNotIn('Draft', statuses)

    def test_generate_artwork_number_api_requires_design(self):
        self.client.force_login(self.marketer)
        self.assertEqual(
            self.client.get('/artwork/api/generate-artwork-number/').status_code,
            403,
        )
        self.client.force_login(self.designer)
        response = self.client.get('/artwork/api/generate-artwork-number/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['artwork_no'].startswith('ART-'))

    def test_completed_pdf_download_matches_view_access(self):
        self.assertTrue(_can_download_pdf(self.completed, self.designer))
        self.assertTrue(_can_download_pdf(self.other_completed, self.marketer))
        self.assertFalse(_can_download_pdf(self.other_completed, self.designer))
        self.assertTrue(_can_download_pdf(self.completed, self.procurement))
        self.assertFalse(_can_download_pdf(self.completed, self.outsider))

    def test_outsider_cannot_view_others_artwork(self):
        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(f'/artwork/{self.completed.artwork_no}/detail/').status_code,
            403,
        )
        response = self.client.get('/artwork/all/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'ACL Completed Item')
        self.assertEqual(response.context['artworks'], [])

    def test_stage_owner_can_open_approval_page(self):
        self.client.force_login(self.marketer)
        response = self.client.get(
            f'/artwork/{self.marketing_pending.artwork_no}/marketing-approval/'
        )
        self.assertEqual(response.status_code, 200)

    def test_procurement_can_reopen_filled_sap(self):
        self.completed.sap_material_code = 'MAT-1'
        self.completed.sap_material_description = 'Filled'
        self.completed.save(update_fields=['sap_material_code', 'sap_material_description'])
        self.client.force_login(self.procurement)
        response = self.client.get(f'/artwork/{self.completed.artwork_no}/detail/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Edit SAP Details')
        self.assertEqual(
            self.client.get(f'/artwork/{self.completed.artwork_no}/procurement/').status_code,
            200,
        )

    def test_ops_creator_keeps_own_artwork_in_lists(self):
        """Ops department filter must not hide the user's own submissions."""
        Group.objects.get_or_create(name='OPERATIONS_HOD')
        oils_hod = User.objects.create_user('acl_oils_hod', password='pass')
        oils_hod.groups.add(Group.objects.get(name='OPERATIONS_HOD'))
        ProductCategory.objects.create(
            name='Oils', hod=oils_hod, is_active=True,
        )
        # Own submission pending Ops under a different mapped category name.
        own_other_dept = ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='Own Cross Dept',
            product_category='Soap',
            created_by=oils_hod,
            status='Pending: Operations HOD Approval',
        )
        ProductCategory.objects.create(
            name='Soap',
            hod=User.objects.create_user('acl_soap_hod', password='pass'),
            is_active=True,
        )
        Group.objects.get(name='OPERATIONS_HOD')  # soap hod not in group yet
        visible = _artworks_for_user(oils_hod)
        self.assertTrue(visible.filter(pk=own_other_dept.pk).exists())
        self.assertTrue(_can_view(own_other_dept, oils_hod))
        self.client.force_login(oils_hod)
        response = self.client.get('/artwork/all/')
        self.assertContains(response, 'Own Cross Dept')
        # Must not get a Review button for another department's mapped item
        art = next(a for a in response.context['artworks'] if a.pk == own_other_dept.pk)
        self.assertFalse(art.can_review)

class DeadlineReminderNotificationTests(TestCase):
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_deadline_reminder_ccs_creator(self):
        from django.core import mail

        Group.objects.get_or_create(name='MARKETING_SALES')
        designer = User.objects.create_user(
            'reminder_designer', password='pass', email='creator@example.com',
        )
        marketer = User.objects.create_user(
            'reminder_marketer', password='pass', email='marketer@example.com',
        )
        marketer.groups.add(Group.objects.get(name='MARKETING_SALES'))
        artwork = ArtworkRequest.objects.create(
            artwork_no=generate_artwork_number(),
            product_name='Reminder Product',
            created_by=designer,
            status='Pending: Marketing & Sales Approval',
        )
        mail.outbox.clear()
        ArtworkNotificationService.send_deadline_reminder(artwork, 'marketing')
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn('marketer@example.com', msg.to)
        self.assertIn('creator@example.com', msg.cc)

