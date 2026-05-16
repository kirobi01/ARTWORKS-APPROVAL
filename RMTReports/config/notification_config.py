# RMTReports/config/notification_config.py

# Define default CC recipients that should receive all notifications
DEFAULT_CC = ['support.user5@kapa-oil.com', 'purchase.user2@kapa-oil.com']

APPROVAL_CONFIG = {
   'HOD_PURCHASE': {
       'display': 'HOD Purchase Review', 
       'next_stage': 'ManagementApproval',
       'recipients': {
           'approved': {
               'to': ['management@kapa-oil.com'],
               'cc': DEFAULT_CC + ['creator_email'],
               'subject': 'RMTR {rmtr_no} - Approved by HOD Purchase, Pending Management Review',
               'template': 'emails/rmtr_notifications.html'
           },
           'rejected': {
               'to': ['creator_email'],
               'cc': DEFAULT_CC,
               'subject': 'RMTR {rmtr_no} - Rejected by HOD Purchase',
               'template': 'emails/rmtr_notifications.html'
           }
       }
   },
   'MANAGEMENT': {
       'display': 'Management Review',
       'next_stage': 'FMApproval', 
       'recipients': {
           'approved': {
               'to': ['fm@kapa-oil.com'],
               'cc': DEFAULT_CC + ['hod_purchase@kapa-oil.com', 'creator_email'],
               'subject': 'RMTR {rmtr_no} - Approved by Management, Pending FM Review',
               'template': 'emails/rmtr_notifications.html'
           },
           'rejected': {
               'to': ['creator_email', 'hod_purchase@kapa-oil.com'],
               'cc': DEFAULT_CC,
               'subject': 'RMTR {rmtr_no} - Rejected by Management',
               'template': 'emails/rmtr_notifications.html'
           }
       }
   },
   'FM': {
       'display': 'FM Review',
       'next_stage': 'HODApproval',
       'recipients': {
           'approved': {
               'to': ['hod@kapa-oil.com'],
               'cc': DEFAULT_CC + ['management@kapa-oil.com', 'creator_email'],
               'subject': 'RMTR {rmtr_no} - Approved by FM, Pending HOD Review',
               'template': 'emails/rmtr_notifications.html'
           },
           'rejected': {
               'to': ['creator_email', 'management@kapa-oil.com'],
               'cc': DEFAULT_CC,
               'subject': 'RMTR {rmtr_no} - Rejected by FM',
               'template': 'emails/rmtr_notifications.html'
           }
       }
   },
   'HOD': {
       'display': 'HOD Review',
       'next_stage': 'QCTesting',
       'recipients': {
           'approved': {
               'to': ['qc@kapa-oil.com'],
               'cc': DEFAULT_CC + ['fm@kapa-oil.com', 'creator_email'],
               'subject': 'RMTR {rmtr_no} - Approved by HOD, Pending QC Testing',
               'template': 'emails/rmtr_notifications.html'
           },
           'rejected': {
               'to': ['creator_email', 'fm@kapa-oil.com'],
               'cc': DEFAULT_CC,
               'subject': 'RMTR {rmtr_no} - Rejected by HOD',
               'template': 'emails/rmtr_notifications.html'
           }
       }
   },
   'QC': {
       'display': 'QC Testing',
       'next_stage': 'QAOApproval',
       'recipients': {
           'approved': {
               'to': ['qao@kapa-oil.com'],
               'cc': DEFAULT_CC + ['hod@kapa-oil.com', 'creator_email'],
               'subject': 'RMTR {rmtr_no} - Testing Complete, Pending QAO Review',
               'template': 'emails/rmtr_notifications.html'
           },
           'rejected': {
               'to': ['creator_email', 'hod@kapa-oil.com'],
               'cc': DEFAULT_CC,
               'subject': 'RMTR {rmtr_no} - Testing Failed',
               'template': 'emails/rmtr_notifications.html'
           }
       }
   },
   'QAO': {
       'display': 'QAO Review',
       'next_stage': 'HODTestApproval',
       'recipients': {
           'approved': {
               'to': ['hod@kapa-oil.com'],
               'cc': DEFAULT_CC + ['qc@kapa-oil.com', 'creator_email'],
               'subject': 'RMTR {rmtr_no} - QAO Approved, Pending HOD Test Review',
               'template': 'emails/rmtr_notifications.html'
           },
           'rejected': {
               'to': ['creator_email', 'qc@kapa-oil.com'],
               'cc': DEFAULT_CC,
               'subject': 'RMTR {rmtr_no} - QAO Rejected Test Results',
               'template': 'emails/rmtr_notifications.html'
           }
       }
   },
   'HOD_TEST': {
       'display': 'HOD Test Review',
       'next_stage': 'FMTestApproval',
       'recipients': {
           'approved': {
               'to': ['fm@kapa-oil.com'],
               'cc': DEFAULT_CC + ['qao@kapa-oil.com', 'creator_email'],
               'subject': 'RMTR {rmtr_no} - HOD Approved Test Results, Pending FM Review',
               'template': 'emails/rmtr_notifications.html'
           },
           'rejected': {
               'to': ['creator_email', 'qao@kapa-oil.com'],
               'cc': DEFAULT_CC,
               'subject': 'RMTR {rmtr_no} - HOD Rejected Test Results',
               'template': 'emails/rmtr_notifications.html'
           }
       }
   },
   'FM_TEST': {
       'display': 'FM Test Review',
       'next_stage': 'ManagementTestApproval',
       'recipients': {
           'approved': {
               'to': ['management@kapa-oil.com'],
               'cc': DEFAULT_CC + ['hod@kapa-oil.com', 'creator_email'],
               'subject': 'RMTR {rmtr_no} - FM Approved Test Results, Pending Management Review',
               'template': 'emails/rmtr_notifications.html'
           },
           'rejected': {
               'to': ['creator_email', 'hod@kapa-oil.com'],
               'cc': DEFAULT_CC,
               'subject': 'RMTR {rmtr_no} - FM Rejected Test Results',
               'template': 'emails/rmtr_notifications.html'
           }
       }
   },
   'MANAGEMENT_TEST': {
       'display': 'Management Test Review',
       'next_stage': 'MilanApproval',
       'recipients': {
           'approved': {
               'to': ['milan@kapa-oil.com'],
               'cc': DEFAULT_CC + [
                   'fm@kapa-oil.com',
                   'creator_email',
                   'hod@kapa-oil.com'
               ],
               'subject': 'RMTR {rmtr_no} - Management Approved Test Results, Pending Milan Review',
               'template': 'emails/rmtr_notifications.html'
           },
           'rejected': {
               'to': ['creator_email', 'fm@kapa-oil.com'],
               'cc': DEFAULT_CC + ['hod@kapa-oil.com'],
               'subject': 'RMTR {rmtr_no} - Management Rejected Test Results',
               'template': 'emails/rmtr_notifications.html'
           }
       }
   },
   'MILAN': {
       'display': 'Milan Final Review',
       'next_stage': 'Completed',
       'recipients': {
           'approved': {
               'to': ['creator_email'],
               'cc': DEFAULT_CC + [
                   'management@kapa-oil.com',
                   'fm@kapa-oil.com',
                   'hod@kapa-oil.com',
                   'qc@kapa-oil.com'
               ],
               'subject': 'RMTR {rmtr_no} - Final Approval Complete',
               'template': 'emails/rmtr_notifications.html'
           },
           'rejected': {
               'to': ['creator_email'],
               'cc': DEFAULT_CC + [
                   'management@kapa-oil.com',
                   'fm@kapa-oil.com',
                   'hod@kapa-oil.com',
                   'qc@kapa-oil.com'
               ],
               'subject': 'RMTR {rmtr_no} - Rejected by Milan',
               'template': 'emails/rmtr_notifications.html'
           }
       }
   }
}

# Email Configuration
EMAIL_CONFIG = {
   'default_sender': 'kapaportal@kapa-oil.com',
   'always_cc': DEFAULT_CC,
   'smtp_settings': {
       'host': 'your-smtp-server',
       'port': 587,
       'use_tls': True
   }
}

# Status Flow Configuration
STATUS_FLOW = {
   'pending': 'pending_hod_purchase',
   'pending_hod_purchase': 'pending_management',
   'pending_management': 'pending_fm',
   'pending_fm': 'pending_hod',
   'pending_hod': 'pending_qc',
   'pending_qc': 'pending_qao',
   'pending_qao': 'pending_hod_test',
   'pending_hod_test': 'pending_fm_test',
   'pending_fm_test': 'pending_management_test',
   'pending_management_test': 'pending_milan',
   'pending_milan': 'completed',
   'rejected': 'rejected'
}