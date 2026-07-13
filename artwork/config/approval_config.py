"""Artwork approval workflow configuration."""

ARTWORK_STATUS_CONFIG = {
    'draft': {
        'display': 'Draft',
        'db_status': 'Draft',
        'group': 'DESIGN',
        'next_stage': 'marketing',
        'next_status': 'Pending: Marketing & Sales Approval',
        'timeline_hours': None,
        'approval_url_name': None,
    },
    'design_created': {
        'display': 'Design Created',
        'db_status': 'Design Created',
        'group': 'DESIGN',
        'next_stage': 'marketing',
        'next_status': 'Pending: Marketing & Sales Approval',
        'timeline_hours': None,
        'approval_url_name': None,
    },
    'marketing': {
        'display': 'Marketing & Sales',
        'db_status': 'Pending: Marketing & Sales Approval',
        'group': 'MARKETING_SALES',
        'next_stage': 'qa',
        'next_status': 'Pending: Quality Assurance Approval',
        'timeline_hours': 24,
        'approval_url_name': 'marketing-approval',
        'email_to_key': 'marketing_head',
        'approval_template': 'artwork_emails/marketing_approval.html',
        'rejection_template': 'artwork_emails/marketing_rejection.html',
        'field_prefix': 'marketing',
    },
    'qa': {
        'display': 'Quality Assurance',
        'db_status': 'Pending: Quality Assurance Approval',
        'group': 'QUALITY_ASSURANCE',
        'next_stage': 'operations_hod',
        'next_status': 'Pending: Operations HOD Approval',
        'timeline_hours': 24,
        'approval_url_name': 'qa-approval',
        'email_to_key': 'qa_officer',
        'approval_template': 'artwork_emails/qa_approval.html',
        'rejection_template': 'artwork_emails/qa_rejection.html',
        'field_prefix': 'qa',
    },
    'operations_hod': {
        'display': 'Operations HOD',
        'db_status': 'Pending: Operations HOD Approval',
        'group': 'OPERATIONS_HOD',
        'next_stage': 'product_dev',
        'next_status': 'Pending: Product Development Approval',
        'timeline_hours': 24,
        'approval_url_name': 'operations-approval',
        'email_to_key': 'operations_hod',
        'approval_template': 'artwork_emails/operations_approval.html',
        'rejection_template': 'artwork_emails/operations_rejection.html',
        'field_prefix': 'operations_hod',
    },
    'product_dev': {
        'display': 'Product Development',
        'db_status': 'Pending: Product Development Approval',
        'group': 'PRODUCT_DEVELOPMENT',
        'next_stage': 'milan',
        'next_status': 'Pending: Milan Shah Approval',
        'timeline_hours': 24,
        'approval_url_name': 'product-dev-approval',
        'email_to_key': 'product_dev_head',
        'approval_template': 'artwork_emails/product_dev_approval.html',
        'rejection_template': 'artwork_emails/product_dev_rejection.html',
        'field_prefix': 'product_dev',
    },
    'milan': {
        'display': 'Director — Milan Shah',
        'db_status': 'Pending: Milan Shah Approval',
        'group': 'MILAN',
        'next_stage': 'completed',
        'next_status': 'Completed / Approved',
        'timeline_hours': 24,
        'approval_url_name': 'milan-approval',
        'email_to_key': 'milan',
        'approval_template': 'artwork_emails/milan_approval.html',
        'rejection_template': 'artwork_emails/milan_rejection.html',
        'field_prefix': 'milan',
    },
    'design_revision': {
        'display': 'Design Revision',
        'db_status': 'Pending: Design Revision',
        'group': 'DESIGN',
        'next_stage': 'marketing',
        'next_status': 'Pending: Marketing & Sales Approval',
        'timeline_hours': None,
        'approval_url_name': None,
    },
    'completed': {
        'display': 'Completed / Approved',
        'db_status': 'Completed / Approved',
        'group': None,
        'next_stage': None,
        'next_status': None,
        'timeline_hours': None,
        'approval_url_name': None,
        'final_template': 'artwork_emails/final_approved.html',
    },
}

STAGE_ORDER = ['marketing', 'qa', 'operations_hod', 'product_dev', 'milan']

STATUS_TO_STAGE = {
    cfg['db_status']: key
    for key, cfg in ARTWORK_STATUS_CONFIG.items()
    if 'field_prefix' in cfg
}

GROUP_STATUS_MAPPING = {
    'DESIGN': ['Draft', 'Design Created', 'Pending: Design Revision'],
    'MARKETING_SALES': ['Pending: Marketing & Sales Approval'],
    'QUALITY_ASSURANCE': ['Pending: Quality Assurance Approval'],
    'OPERATIONS_HOD': ['Pending: Operations HOD Approval'],
    'PRODUCT_DEVELOPMENT': ['Pending: Product Development Approval'],
    'MILAN': ['Pending: Milan Shah Approval'],
    'PROCUREMENT': ['Completed / Approved'],
    'ADMIN': [cfg['db_status'] for cfg in ARTWORK_STATUS_CONFIG.values()],
}

DEFAULT_LOGO_NAMES = [
    'Kapa', 'Dust Bin', 'QMS', 'Kuboresha Afya', 'KEBS',
    'Recycling', 'Touch of Kenya', 'Halal', 'Cholesterol Free',
]

ALLOWED_UPLOAD_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.pdf', '.ai', '.eps', '.tiff', '.tif', '.svg',
}

ALLOWED_MIME_TYPES = {
    'image/jpeg', 'image/png', 'image/tiff', 'image/svg+xml',
    'application/pdf', 'application/postscript', 'application/illustrator',
    'application/octet-stream',
}

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB

CHUNK_SIZE = 2 * 1024 * 1024  # 2 MB chunks

DRAFT_STATUS = 'Draft'
COMPLETED_STATUS = 'Completed / Approved'
