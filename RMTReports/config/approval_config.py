"""
Configuration file for RMTR approval flow
"""
from RMTReports.models import (
    HODPurchaseApproval,
    ManagementApproval,
    FMApproval,
    HODApproval,
    QAOTestApproval,
    HODTestApproval,
    FMTestApproval,
    ManagementTestApproval,
    MilanTestApproval
)

APPROVAL_MODELS = {
    'HOD_PURCHASE': HODPurchaseApproval,
    'MANAGEMENT': ManagementApproval,
    'FM': FMApproval,
    'HOD': HODApproval,
    'QAO_TEST': QAOTestApproval,
    'HOD_TEST': HODTestApproval,
    'FM_TEST': FMTestApproval,
    'MANAGEMENT_TEST': ManagementTestApproval,
    'MILAN_TEST': MilanTestApproval
}

TEMPLATE_MAPPING = {
    'HOD_PURCHASE': 'hod_purchase_approval.html',
    'MANAGEMENT': 'management_approval.html',
    'FM': 'fm_approval.html',
    'HOD': 'hod_approval.html',
    'QAO_TEST': 'qao_test_approval.html',
    'HOD_TEST': 'hod_test_approval.html',
    'FM_TEST': 'fm_test_approval.html',
    'MANAGEMENT_TEST': 'management_test_approval.html',
    'MILAN_TEST': 'milan_test_approval.html'
}

# Define the flow of approval statuses
STATUS_FLOW = {
    'DRAFT': {
        'next': 'HOD_PENDING',
        'previous': None
    },
    'HOD_PENDING': {
        'next': 'FM_PENDING',
        'previous': 'DRAFT'
    },
    'FM_PENDING': {
        'next': 'MANAGEMENT_PENDING',
        'previous': 'HOD_PENDING'
    },
    'MANAGEMENT_PENDING': {
        'next': 'QAO_TEST_PENDING',
        'previous': 'FM_PENDING'
    },
    'QAO_TEST_PENDING': {
        'next': 'HOD_TEST_PENDING',
        'previous': 'MANAGEMENT_PENDING'
    },
    'HOD_TEST_PENDING': {
        'next': 'FM_TEST_PENDING',
        'previous': 'QAO_TEST_PENDING'
    },
    'FM_TEST_PENDING': {
        'next': 'MANAGEMENT_TEST_PENDING',
        'previous': 'HOD_TEST_PENDING'
    },
    'MANAGEMENT_TEST_PENDING': {
        'next': 'MILAN_TEST_PENDING',
        'previous': 'FM_TEST_PENDING'
    },
    'MILAN_TEST_PENDING': {
        'next': 'COMPLETED',
        'previous': 'MANAGEMENT_TEST_PENDING'
    },
    'COMPLETED': {
        'next': None,
        'previous': 'MILAN_TEST_PENDING'
    },
    'REJECTED': {
        'next': None,
        'previous': None
    }
}

# Define who should be notified at each stage
NOTIFICATION_MAPPING = {
    'HOD_PENDING': ['hod_group'],
    'FM_PENDING': ['fm_group'],
    'MANAGEMENT_PENDING': ['management_group'],
    'QAO_TEST_PENDING': ['qao_group'],
    'HOD_TEST_PENDING': ['hod_test_group'],
    'FM_TEST_PENDING': ['fm_test_group'],
    'MANAGEMENT_TEST_PENDING': ['management_test_group'],
    'MILAN_TEST_PENDING': ['milan_test_group'],
    'COMPLETED': ['requester', 'all_approvers'],
    'REJECTED': ['requester', 'previous_approver']
}

# Email subject templates for different notifications
EMAIL_SUBJECTS = {
    'NEW_REQUEST': 'New RMTR Request #{request_id} Requires Your Approval',
    'APPROVED': 'RMTR Request #{request_id} Has Been Approved by {approver}',
    'REJECTED': 'RMTR Request #{request_id} Has Been Rejected by {approver}',
    'COMPLETED': 'RMTR Request #{request_id} Has Been Completed',
    'REMINDER': 'Reminder: RMTR Request #{request_id} Awaiting Your Approval',
    'UPDATED': 'RMTR Request #{request_id} Has Been Updated',
    'COMMENT_ADDED': 'New Comment on RMTR Request #{request_id}',
    'STATUS_CHANGE': 'Status Changed for RMTR Request #{request_id}',
    'DOCUMENT_ADDED': 'New Document Added to RMTR Request #{request_id}'
}

# Optional: Define status display names for UI
STATUS_DISPLAY_NAMES = {
    'DRAFT': 'Draft',
    'HOD_PENDING': 'Pending HOD Approval',
    'FM_PENDING': 'Pending FM Approval',
    'MANAGEMENT_PENDING': 'Pending Management Approval',
    'QAO_TEST_PENDING': 'Pending QAO Test Approval',
    'HOD_TEST_PENDING': 'Pending HOD Test Approval',
    'FM_TEST_PENDING': 'Pending FM Test Approval',
    'MANAGEMENT_TEST_PENDING': 'Pending Management Test Approval',
    'MILAN_TEST_PENDING': 'Pending Milan Test Approval',
    'COMPLETED': 'Completed',
    'REJECTED': 'Rejected'
}

# Optional: Define permission requirements for each status
PERMISSION_REQUIREMENTS = {
    'HOD_PENDING': 'can_approve_hod',
    'FM_PENDING': 'can_approve_fm',
    'MANAGEMENT_PENDING': 'can_approve_management',
    'QAO_TEST_PENDING': 'can_approve_qao_test',
    'HOD_TEST_PENDING': 'can_approve_hod_test',
    'FM_TEST_PENDING': 'can_approve_fm_test',
    'MANAGEMENT_TEST_PENDING': 'can_approve_management_test',
    'MILAN_TEST_PENDING': 'can_approve_milan_test'
}