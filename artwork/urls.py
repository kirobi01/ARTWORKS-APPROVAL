from django.urls import path
from . import views

# Order matters: static paths before <str:artwork_no> catch-alls.
urlpatterns = [
    # Auth
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Artwork lists (static segments first)
    path('create/', views.artwork_create, name='artwork-create'),
    path('logo-icons/<int:pk>/', views.logo_template_icon, name='logo-template-icon'),
    path('logos/', views.logo_library, name='logo-library'),
    path('logos/<int:pk>/edit/', views.logo_library_edit, name='logo-library-edit'),
    path('logos/<int:pk>/toggle/', views.logo_library_toggle, name='logo-library-toggle'),
    path('all/', views.artwork_all, name='artwork-all'),
    path('my/', views.artwork_my, name='artwork-my'),
    path('drafts/', views.artwork_drafts, name='artwork-drafts'),
    path('pending/', views.artwork_pending, name='artwork-pending'),
    path('completed/', views.artwork_completed, name='artwork-completed'),

    # API (before artwork_no patterns)
    path('api/generate-artwork-number/', views.api_generate_artwork_number, name='api-generate-artwork-number'),

    # Edit uses static prefix
    path('edit/<str:artwork_no>/', views.artwork_edit, name='artwork-edit'),

    # Artwork_no routes — specific suffixes before generic detail
    path('<str:artwork_no>/marketing-approval/', views.marketing_approval, name='marketing-approval'),
    path('<str:artwork_no>/qa-approval/', views.qa_approval, name='qa-approval'),
    path('<str:artwork_no>/operations-approval/', views.operations_approval, name='operations-approval'),
    path('<str:artwork_no>/product-dev-approval/', views.product_dev_approval, name='product-dev-approval'),
    path('<str:artwork_no>/milan-approval/', views.milan_approval, name='milan-approval'),
    path('<str:artwork_no>/procurement/', views.procurement_view, name='procurement'),
    path('<str:artwork_no>/upload-chunk/', views.upload_chunk, name='upload-chunk'),
    path('<str:artwork_no>/attachments/', views.attachment_list, name='attachment-list'),
    path('<str:artwork_no>/download/<int:file_id>/', views.attachment_download, name='attachment-download'),
    path('<str:artwork_no>/preview/<int:file_id>/', views.attachment_preview, name='attachment-preview'),
    path('<str:artwork_no>/set-primary/<int:file_id>/', views.set_primary_attachment, name='set-primary'),
    path('<str:artwork_no>/delete-attachment/<int:file_id>/', views.delete_attachment, name='delete-attachment'),
    path('<str:artwork_no>/download-pdf/', views.download_artwork_pdf, name='download-artwork-pdf'),
    path('api/<str:artwork_no>/details/', views.api_artwork_details, name='api-artwork-details'),
    path('api/<str:artwork_no>/comments/', views.api_artwork_comments, name='api-artwork-comments'),
    path('<str:artwork_no>/detail/', views.artwork_detail, name='artwork-detail'),
]
