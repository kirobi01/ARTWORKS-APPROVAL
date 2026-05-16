"""
URL configuration for RMTr project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# main urls.py
from django.urls import path, include
from django.contrib import admin
from django.views.generic import RedirectView
from RMTReports.views import * 

urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentication and root
    path('', login_view, name='home'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),

    # Main pages - both hyphenated and underscore versions
    path('dashboard/', dashboard, name='dashboard'),
    path('test-request/', test_request, name='test-request'),
    path('test_request/', test_request, name='test_request'),
    path('test-request/<str:rmtr_no>/', test_request, name='test-request-with-id'),
    path('test_request/<str:rmtr_no>/', test_request, name='test_request_with_id'),
    path('submit-form/', submit_form, name='submit-form'),
    path('submit_form/', submit_form, name='submit_form'),
    path('test/', test_view, name='test'),
    path('test/<str:rmtr_no>/', test_request, name='test-request'),
    
    # Fill page routes
    path('fill-page/<str:rmtr_no>/', fill_page, name='fill-page'),
    path('fill_page/<str:rmtr_no>/', fill_page, name='fill_page'),
    path('fill-page/<pk>/', fill_page, name='fill-page-pk'),
    path('fill_page/<pk>/', fill_page, name='fill_page_pk'),
    
    # Target route
    path('get-target-route/', get_target_route, name='get-target-route'),
    path('get_target_route/', get_target_route, name='get_target_route'),
    
    # Report listings
    path('pending/', pending_reports, name='pending'),
    path('pending-reports/', pending_reports, name='pending-reports'),
    path('pending_reports/', pending_reports, name='pending_reports'),
    path('completed-reports/', completed_reports, name='completed-reports'),
    path('completed_reports/', completed_reports, name='completed_reports'),
    
    #path('new_rmtr/', new_rmtr, name='new_rmtr'),
    path('all_rmtr/', all_rmtr, name='all_rmtr'),
    
    path('all_rmtrs/', all_rmtr, name='all_rmtrs'),
    path('my-rmtr/', my_rmtr, name='my-rmtr'),
    path('my_rmtr/', my_rmtr, name='my_rmtr'),
    path('final-report/', final_report, name='final-report'),
    path('final_report/', final_report, name='final_report'),
    path('create-report/', create_report, name='create-report'),
    path('create_report/', create_report, name='create_report'),
    path('pdf-report/', pdf_report, name='pdf-report'),
    path('pdf_report/', pdf_report, name='pdf_report'),

    # Utility routes
    path('generate-rmtr-number/', generate_rmtr_number, name='generate-rmtr-number'),
    path('generate_rmtr_number/', generate_rmtr_number, name='generate_rmtr_number'),
    path('check-pending-rmtrs/', check_pending_rmtrs, name='check-pending-rmtrs'),
    path('check_pending_rmtrs/', check_pending_rmtrs, name='check_pending_rmtrs'),
    path('upload/', upload_rmtr_image, name='upload_rmtr_image'),
    path('rmtr/<str:rmtr_no>/download/', download_rmtr_pdf, name='download-rmtr-pdf'),
    path('download/<str:rmtr_no>/', download_rmtr_pdf, name='download_rmtr_pdf'),
    
    # Approval routes - both formats
    path('approval/<str:rmtr_no>/hod-purchase/', hod_purchase_approval, name='hod-purchase-approval'),
    path('approval/<str:rmtr_no>/hod_purchase/', hod_purchase_approval, name='hod_purchase_approval'),
    path('approval/<str:rmtr_no>/', process_approval, name='process-approval'),
    path('approval/<str:rmtr_no>/', process_approval, name='process_approval'),
    path('edit-rmtr/<str:rmtr_no>/', edit_rmtr, name='edit-rmtr'),
    path('edit_rmtr/<str:rmtr_no>/', edit_rmtr, name='edit_rmtr'),
    path('approval-page/', approval_page, name='approval-page'),
    path('approval_page/', approval_page, name='approval_page'),
    path('approval-page/<int:rmtr_no>/', approval_page, name='approval-page-with-id'),
    path('approval_page/<int:rmtr_no>/', approval_page, name='approval_page_with_id'),
    
    # HOD approval routes
    path('hod-purchase-approval/<str:rmtr_no>/', hod_purchase_approval, name='hod-purchase-approval'),
    path('hod_purchase_approval/<str:rmtr_no>/', hod_purchase_approval, name='hod_purchase_approval'),
    path('hod-approval/', hod_approval, name='hod-approval'),
    path('hod_approval/', hod_approval, name='hod_approval'),
    path('hod-approval/<str:rmtr_no>/', hod_approval, name='hod-approval-with-id'),
    path('hod_approval/<str:rmtr_no>/', hod_approval, name='hod_approval_with_id'),
    path('hod-test-approval/', hod_test_approval, name='hod-test-approval'),
    path('hod_test_approval/', hod_test_approval, name='hod_test_approval'),
    path('hod-test-approval/<str:rmtr_no>/', hod_test_approval, name='hod-test-approval-with-id'),
    path('hod_test_approval/<str:rmtr_no>/', hod_test_approval, name='hod_test_approval_with_id'),
    
    # FM approval routes
    path('fm-approval/', fm_approval, name='fm-approval'),
    path('fm_approval/', fm_approval, name='fm_approval'),
    path('fm-approval/<str:rmtr_no>/', fm_approval, name='fm-approval-with-id'),
    path('fm_approval/<str:rmtr_no>/', fm_approval, name='fm_approval_with_id'),
    path('fm-test-approval/', fm_test_approval, name='fm-test-approval'),
    path('fm_test_approval/', fm_test_approval, name='fm_test_approval'),
    path('fm-test-approval/<str:rmtr_no>/', fm_test_approval, name='fm-test-approval-with-id'),
    path('fm_test_approval/<str:rmtr_no>/', fm_test_approval, name='fm_test_approval_with_id'),
    
    # Management approval routes
    path('management-approval/', management_approval, name='management-approval'),
    path('management_approval/', management_approval, name='management_approval'),
    path('management-approval/<str:rmtr_no>/', management_approval, name='management-approval-with-id'),
    path('management_approval/<str:rmtr_no>/', management_approval, name='management_approval_with_id'),
    path('management-approval-2/<str:rmtr_no>/', management_approval_2, name='management-approval-2'),
    path('management_approval_2/<str:rmtr_no>/', management_approval_2, name='management_approval_2'),
    path('management-test-approval/', management_test_approval, name='management-test-approval'),
    path('management_test_approval/', management_test_approval, name='management_test_approval'),
    path('management-test-approval/<str:rmtr_no>/', management_test_approval, name='management-test-approval-with-id'),
    path('management_test_approval/<str:rmtr_no>/', management_test_approval, name='management_test_approval_with_id'),
    
    # QAO and Milan approval routes
    path('qao-test-approval/', qao_test_approval, name='qao-test-approval'),
    path('qao_test_approval/', qao_test_approval, name='qao_test_approval'),
    path('qao-test-approval/<str:rmtr_no>/', qao_test_approval, name='qao-test-approval-with-id'),
    path('qao_test_approval/<str:rmtr_no>/', qao_test_approval, name='qao_test_approval_with_id'),
    path('milan-approval/<str:rmtr_no>/', milan_approval, name='milan-approval'),
    path('milan_approval/<str:rmtr_no>/', milan_approval, name='milan_approval'),
    
    # Retest routes
    path('retest-request/<str:rmtr_no>/', retest_request, name='retest-request'),
    path('retest_request/<str:rmtr_no>/', retest_request, name='retest_request'),
    
    # API Endpoints - both formats
    path('api/rmtr-tests/<str:rmtr_no>/', get_rmtr_tests, name='get-rmtr-tests'),
    path('api/rmtr_tests/<str:rmtr_no>/', get_rmtr_tests, name='get_rmtr_tests'),
    path('api/rmtr-reports/<str:rmtr_no>/', get_rmtr_report, name='get-rmtr-report'),
    path('api/rmtr_reports/<str:rmtr_no>/', get_rmtr_report, name='get_rmtr_report'),
    path('api/suppliers/', get_suppliers, name='get-suppliers'),
    path('api/plant-hod-data/', plant_hod_data, name='plant-hod-data'),
    path('api/plant_hod_data/', plant_hod_data, name='plant_hod_data'),
    path('api/fetch-material-data/', fetch_material_data, name='fetch-material-data'),
    path('api/fetch_material_data/', fetch_material_data, name='fetch_material_data'),
    path('api/report/<str:rmtr_no>/', get_report_data, name='get-report-data'),
    path('api/report/<str:rmtr_no>/', get_report_data, name='get_report_data'),
    path('api/check-rmtr/<str:rmtr_no>/', check_rmtr, name='check-rmtr'),
    path('api/check_rmtr/<str:rmtr_no>/', check_rmtr, name='check_rmtr'),
    
    # Test related routes
    path('rmtr/<str:rmtr_no>/tests/', get_rmtr_tests, name='rmtr-tests'),
    path('rmtr/<str:rmtr_id>/tests/', get_rmtr_tests, name='get-rmtr-tests'),
    path('rmtr/<int:rmtr_id>/tests/', get_rmtr_tests, name='rmtr-tests-int'),
    
    # Supplier management routes
    path('manage-suppliers/', manage_suppliers, name='manage-suppliers'),
    path('manage_suppliers/', manage_suppliers, name='manage_suppliers'),
    path('suppliers/', manage_suppliers, name='suppliers'),
    path('create-supplier/', create_supplier, name='create-supplier'),
    path('create_supplier/', create_supplier, name='create_supplier'),
    
    # Direct data routes
    path('get-plant-hod-data/', plant_hod_data, name='plant-hod-data'),
    path('get_plant_hod_data/', plant_hod_data, name='plant_hod_data'),
    path('fetch-material-data/', fetch_material_data, name='fetch-material-data'),
    path('fetch_material_data/', fetch_material_data, name='fetch_material_data'),
    path('check-rmtr/', check_rmtr, name='check-rmtr'),
    path('check_rmtr/', check_rmtr, name='check_rmtr'),
    
    # Import routes - both formats
    path('imp_test_request/', imp_test_request, name='imp_test_request'),
    path('imp-test-request/', imp_test_request, name='imp-test-request'),
    path('imp_test_request/<str:imp_rmtr_no>/', imp_test_request, name='imp_test_request_with_id'),
    path('imp-test-request/<str:imp_rmtr_no>/', imp_test_request, name='imp-test-request-with-id'),
    path('generate-imp-rmtr-number/', generate_imp_rmtr_number, name='generate-imp-rmtr-number'),
    path('generate_imp_rmtr_number/', generate_imp_rmtr_number, name='generate_imp_rmtr_number'),
    
    path('imp_pending/', imp_pending, name='imp_pending'),
    path('imp-pending/', imp_pending, name='imp-pending'),
    path('imp_completed_reports/', imp_completed_reports, name='imp_completed_reports'),
    path('imp-completed-reports/', imp_completed_reports, name='imp-completed-reports'),
    
    # Import approval routes
    path('imp_hod_purchase_approval/<str:imp_rmtr_no>/', imp_hod_purchase_approval, name='imp_hod_purchase_approval'),
    path('imp-hod-purchase-approval/<str:imp_rmtr_no>/', imp_hod_purchase_approval, name='imp-hod-purchase-approval'),
    path('imp_management_approval/<str:imp_rmtr_no>/', imp_management_approval, name='imp_management_approval'),
    path('imp-management-approval/<str:imp_rmtr_no>/', imp_management_approval, name='imp-management-approval'),
    path('imp_management_approval_2/<str:imp_rmtr_no>/', imp_management_approval_2, name='imp_management_approval_2'),
    path('imp-management-approval-2/<str:imp_rmtr_no>/', imp_management_approval_2, name='imp-management-approval-2'),
    path('imp_fm_approval/<str:imp_rmtr_no>/', imp_fm_approval, name='imp_fm_approval'),
    path('imp-fm-approval/<str:imp_rmtr_no>/', imp_fm_approval, name='imp-fm-approval'),
    path('imp_hod_approval/<str:imp_rmtr_no>/', imp_hod_approval, name='imp_hod_approval'),
    path('imp-hod-approval/<str:imp_rmtr_no>/', imp_hod_approval, name='imp-hod-approval'),
    
    # Import test approval routes
    path('imp_hod_test_approval/<str:imp_rmtr_no>/', imp_hod_test_approval, name='imp_hod_test_approval'),
    path('imp-hod-test-approval/<str:imp_rmtr_no>/', imp_hod_test_approval, name='imp-hod-test-approval'),
    path('imp_fm_test_approval/<str:imp_rmtr_no>/', imp_fm_test_approval, name='imp_fm_test_approval'),
    path('imp-fm-test-approval/<str:imp_rmtr_no>/', imp_fm_test_approval, name='imp-fm-test-approval'),
    path('imp_management_test_approval/<str:imp_rmtr_no>/', imp_management_test_approval, name='imp_management_test_approval'),
    path('imp-management-test-approval/<str:imp_rmtr_no>/', imp_management_test_approval, name='imp-management-test-approval'),
    path('imp_qao_test_approval/<str:imp_rmtr_no>/', imp_qao_test_approval, name='imp_qao_test_approval'),
    path('imp-qao-test-approval/<str:imp_rmtr_no>/', imp_qao_test_approval, name='imp-qao-test-approval'),
    
    # Import other routes
    path('edit_imp_rmtr/<str:imp_rmtr_no>/', edit_imp_rmtr, name='edit_imp_rmtr'),
    path('edit-imp-rmtr/<str:imp_rmtr_no>/', edit_imp_rmtr, name='edit-imp-rmtr'),
    path('imp_fill_page/<str:imp_rmtr_no>/', imp_fill_page, name='imp_fill_page'),
    path('imp-fill-page/<str:imp_rmtr_no>/', imp_fill_page, name='imp-fill-page'),
    path('imp_rmtr/<str:imp_rmtr_no>/tests/', imp_rmtr_tests, name='imp_rmtr_tests'),
    path('imp-rmtr/<str:imp_rmtr_no>/tests/', imp_rmtr_tests, name='imp-rmtr-tests'),
    path('imp_retest_request/<str:imp_rmtr_no>/', imp_retest_request, name='imp_retest_request'),
    path('imp-retest-request/<str:imp_rmtr_no>/', imp_retest_request, name='imp-retest-request'),
    path('imp_milan_approval/<str:imp_rmtr_no>/', imp_milan_approval, name='imp_milan_approval'),
    path('imp-milan-approval/<str:imp_rmtr_no>/', imp_milan_approval, name='imp-milan-approval'),
    
    # Import utility routes
    path('imp_export_to_excel/', imp_export_to_excel, name='imp_export_to_excel'),
    path('imp-export-to-excel/', imp_export_to_excel, name='imp-export-to-excel'),
    path('imp_rmtr/<str:imp_rmtr_no>/download/', imp_download_rmtr_pdf, name='imp_download_rmtr_pdf'),
    path('imp-rmtr/<str:imp_rmtr_no>/download/', imp_download_rmtr_pdf, name='imp-download-rmtr-pdf'),
    
    # Import data routes
    path('imp_report_data/<str:imp_rmtr_no>/', imp_get_report_data, name='imp_report_data'),
    path('imp-report-data/<str:imp_rmtr_no>/', imp_get_report_data, name='imp-report-data'),
    path('imp_rmtr_tests/<str:imp_rmtr_no>/', imp_get_rmtr_tests, name='imp_rmtr_tests_get'),
    path('imp-rmtr-tests/<str:imp_rmtr_no>/', imp_get_rmtr_tests, name='imp-rmtr-tests-get'),
    path('imp_rmtr_report/<str:imp_rmtr_no>/', imp_get_rmtr_report, name='imp_rmtr_report'),
    path('imp-rmtr-report/<str:imp_rmtr_no>/', imp_get_rmtr_report, name='imp-rmtr-report'),
    path('imp_check_rmtr/<str:imp_rmtr_no>/', imp_check_rmtr, name='imp_check_rmtr'),
    path('imp-check-rmtr/<str:imp_rmtr_no>/', imp_check_rmtr, name='imp-check-rmtr'),
    path('imp/api/report/<str:imp_rmtr_no>/', imp_get_report_data, name='imp-get-report-data'),
    path('imp/api/report/<str:imp_rmtr_no>/', imp_get_report_data, name='imp_get_report_data'),
    path('rmtr/<str:rmtr_no>/download/', download_rmtr_pdf, name='download_rmtr_pdf'),
    path('rmtr/<str:rmtr_no>/preview/', preview_rmtr_pdf, name='preview_rmtr_pdf'),
    path('rmtr/imp/<str:rmtr_no>/download/', imp_download_rmtr_pdf, name='imp_rmtr_download_alt'),
    path('rmtr/imp/<str:rmtr_no>/preview/', imp_download_rmtr_pdf, name='imp_rmtr_preview_alt'),
    path('imp-rmtr/<str:rmtr_no>/preview/', preview_rmtr_pdf, name='preview_rmtr_pdf'),
    path('rmtr/imp/<str:rmtr_no>/download/', imp_download_rmtr_pdf, name='imp_rmtr_download_alt'),
    path('rmtr/imp/<str:rmtr_no>/preview/', imp_download_rmtr_pdf, name='imp_rmtr_preview_alt'),
    path('imp-rmtr/<str:rmtr_no>/preview/', preview_rmtr_pdf, name='preview_rmtr_pdf'),
    # API endpoint for test details
    path('rmtr/<str:rmtr_no>/tests/', get_rmtr_tests, name='get_rmtr_tests'),
    
    
    path('rmtr/<str:rmtr_no>/comments/', get_rmtr_comments, name='rmtr-comments'),
    path('api/rmtr/<str:rmtr_no>/comments/', get_rmtr_comments, name='api-rmtr-comments'),
    path('imp/rmtr/<str:imp_rmtr_no>/comments/', get_rmtr_comments, name='imp-rmtr-comments'),
    path('api/imp/rmtr/<str:imp_rmtr_no>/comments/', get_rmtr_comments, name='api-imp-rmtr-comments'),
    # Include all URLs with rmtr/ prefix
    path('rmtr/', include('RMTReports.urls')),
]

# Add static and media files configuration
from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)