
import logging
import json
import pdfkit
from django.db import models, transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Q
from django.template.loader import render_to_string, get_template
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
#from weasyprint import HTML
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods
from rest_framework import status
from django.conf import settings
from django.contrib import messages
from django.template import Library
from .models import RMTRRequest, Plant
import re


import pdfkit
import logging
import base64
from pathlib import Path

   
from django.conf import settings
import os
import mimetypes
import csv
import xlsxwriter
from io import BytesIO
from datetime import datetime, timedelta
from .forms import (
    RawMaterialTestReportForm, RawMaterialForm, RMTRRequestForm, IMP_RMTRRequestForm, ReportForm,
    HODPurchaseApprovalForm, HODApprovalForm, HODTestApprovalForm,
    ManagementApprovalForm, TestResultsForm, MilanTestApprovalForm,
    ManagementTestApprovalForm, FMApprovalForm, FMTestApprovalForm,
    QAOTestApprovalForm
)
from django.core.exceptions import ValidationError
from .models import IMP_RMTRRequest, Supplier, Plant, DocumentAttachment 

from .models import (
    RawMaterialTestReport, TestResult, RMTRRequest, IMP_RMTRRequest, RetestRequest,Approval, Plant, DocumentAttachment,
    Pending_DataFetch, Report, RMTR, Supplier, Material, SubCategory,
    TemporaryReportSession, Test, ApprovedManagement, HODPurchaseApproval,
    HODApproval, HODTestApproval, ManagementApproval, ManagementTestApproval,
    FMApproval, FMTestApproval, TestResults, MilanTestApproval
)
from .services import NotificationService, RMTRStatusManager
from .config import APPROVAL_CONFIG, EMAIL_CONFIG, STATUS_FLOW
from .config.approval_config import APPROVAL_MODELS, TEMPLATE_MAPPING
from .serializers import SupplierCreateSerializer, SupplierSerializer, TestTypeSerializer
from .tasks import generate_pdf_task
import traceback

from rest_framework import serializers



@login_required
def home_view(request):
    form = RawMaterialTestReportForm()  # Initialize the form
    if request.method == 'POST':
        form = RawMaterialTestReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.status = ''
            report.save()
            messages.success(request, 'Report successfully created.')
            return redirect('test_request')
        else:
            messages.error(request, 'There was an issue with your submission. Please correct the errors below.')



# Set up logger
logger = logging.getLogger(__name__)

@login_required
def logout_view(request):
    try:
        username = request.user.username
        logout(request)       
        
        
        messages.success(request, f'Successfully logged out. Goodbye, {username}!')
        
        # Redirect to login page
        return redirect('login')
    
    except Exception as e:
        # error
        logger.error(f"Error in logout_view: {str(e)}")
        
      
        messages.error(request, 'An error occurred during logout. Please try again.')        
       
        return redirect('dashboard')


@login_required
def test_view(request):
    """View for displaying test reports"""
    try:
        pending_reports = RMTRRequest.objects.filter(status='')
        return render(request, 'test.html', {
            'pending_reports': pending_reports
        })
    except Exception as e:
        logger.error(f"Error in test view: {str(e)}")
        messages.error(request, 'Error loading test reports.')
        return redirect('dashboard')
    
    



@login_required
def test_request(request, rmtr_no=None):
    """Handle both new RMTR requests and updates"""
    allowed_groups = ['PURCHASE', 'ADMIN', 'HOD_PURCHASE']
    if not request.user.groups.filter(name__in=allowed_groups).exists():
        return JsonResponse({
            'status': 'error',
            'message': 'Permission denied. You do not have access to this page.'
        }, status=403)
    
    try:
        if request.method == 'POST':
            try:
                # Create new report
                report = RMTRRequest()
                
                # Set the user fields
                report.created_by = request.user
                report.current_user = request.user  

                # Generate new RMTR number
                current_year = timezone.now().year
                try:
                    last_entry = RMTRRequest.objects.filter(
                        rmtr_no__iregex=f'^{current_year}-[0-9]{{4}}$'
                    ).order_by('-rmtr_no').first()
                    
                    if last_entry:
                        year_part, number_part = last_entry.rmtr_no.split('-')
                        new_number = int(number_part) + 1
                    else:
                        new_number = 1
                    
                    report.rmtr_no = f'{current_year}-{str(new_number).zfill(4)}'
                except Exception as e:
                    logger.error(f"Error generating RMTR number: {str(e)}")
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Error generating RMTR number'
                    }, status=500)

                # Set fields from form data
                report.date = request.POST.get('date') or timezone.now().date()
                
                # Fetch the supplier instance
                supplier_id = request.POST.get('supplier')
                if supplier_id:
                    report.supplier = get_object_or_404(Supplier, id=supplier_id)
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Supplier is required'
                    }, status=400)
                
                # Fetch the plant instance
                plant_id = request.POST.get('plant')
                if plant_id:
                    report.plant = get_object_or_404(Plant, id=plant_id)
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Plant is required'
                    }, status=400)

                # Handle approvers
                approvers = request.POST.get('approved-mgt', '').strip()
                if ',' in approvers:
                    first_approver, second_approver = approvers.split(',')
                    report.approved_mgt = first_approver.strip()
                    report.second_approver = second_approver.strip()
                    logger.info(f"Set approvers for RMTR {report.rmtr_no}: First={first_approver.title()}, Second={second_approver.title()}")
                else:
                    report.approved_mgt = approvers
                    report.second_approver = None
                    logger.info(f"Set single approver for RMTR {report.rmtr_no}: {approvers}")

               
                report.material_name= request.POST.get('material_name')
                report.material_type = request.POST.get('material_type', '')
                report.sub_category = request.POST.get('sub_category', '')
                report.tests = request.POST.get('selected_tests', '')
                report.requested_by = request.POST.get('requested-by') or request.user.get_full_name()
                report.justification = request.POST.get('justification')
                report.uom = request.POST.get('uom')
                report.quantity = request.POST.get('quantity')
                report.specs = request.POST.get('specs')
                report.status = 'Pending: HOD Purchase approval'
                report.created_at = timezone.now()
                
                #image upload
                if 'image-upload' in request.FILES:
                    report.image = request.FILES['image-upload']
                
                # Validation of required fields
                required_fields = {
                    'created_by': report.created_by,
                    'material_name':report.material_name,
                    'current_user': report.current_user,
                    'supplier': report.supplier,
                    'plant': report.plant,
                    'material_type': report.material_type,
                    'tests': report.tests,
                    'approved_mgt': report.approved_mgt
                }
                
                missing_fields = [field for field, value in required_fields.items() if not value]
                if missing_fields:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Missing required fields: {", ".join(missing_fields)}'
                    }, status=400)
                
                # Save the report with transaction
                with transaction.atomic():
                    report.save()
                    logger.info(f"Successfully created new report: {report.rmtr_no} by user {request.user}")
                    
                    # Send email notification
                    subject = f'New RMTR Request Created - {report.rmtr_no}'
                    supplier_name = report.supplier.name if report.supplier else "N/A"
                    plant_name = report.plant.name if report.plant else "N/A"
                    message = f"""
                    A new RMTR request has been created with the following details:
                    
                    RMTR Number: {report.rmtr_no}

                    Date: {report.date}

                    Material Name: {report.material_name}

                    Supplier: {supplier_name}

                    Plant: {plant_name}

                    Material Type: {report.material_type}

                    Sub Category: {report.sub_category}

                    Tests Required: {report.tests}

                    Justification: {report.justification}

                    Quantity: {report.quantity} {report.uom}

                    Specifications: {report.specs}

                    First Approver: {report.approved_mgt.title()}
                    
                    Created By: {report.created_by.get_full_name() or report.created_by.username}
                    Date: {report.date_created}

                    Raw Material Test Report Link: http://10.0.0.7:8020
                    """
                    
                    recipients = [
                       'ict@kapa-oil.com',
                       'purchase.user1@kapa-oil.com',
                       'purchase.user2@kapa-oil.com',
                       'purchase.user10@kapa-oil.com',
                       'purchase.user7@kapa-oil.com',
                       'purchase.user9@kapa-oil.com',
                       'purchase.user5@kapa-oil.com',
                       'purchase.user4@kapa-oil.com',
                        request.user.email
                    ]
                    
                    try:
                        send_mail(
                            subject=subject,
                            message=message,
                            from_email='kapaportal@kapa-oil.local',
                            recipient_list=recipients,
                            fail_silently=True,
                        )
                        logger.info(f"Notification email sent for RMTR {report.rmtr_no}")
                    except Exception as e:
                        logger.error(f"Error sending email: {str(e)}")
                    
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Test request created successfully',
                        'redirect': '/dashboard/',
                        'rmtr_no': report.rmtr_no
                    })
                
            except Exception as e:
                logger.error(f"Error creating new report: {str(e)}")
                logger.error(traceback.format_exc())
                return JsonResponse({
                    'status': 'error',
                    'message': str(e)
                }, status=500)
        
        else:  # GET request
            current_year = timezone.now().year
            try:
                last_entry = RMTRRequest.objects.filter(
                    rmtr_no__iregex=f'^{current_year}-[0-9]{{4}}$'
                ).order_by('-rmtr_no').first()
                
                if last_entry:
                    year_part, number_part = last_entry.rmtr_no.split('-')
                    new_number = int(number_part) + 1
                else:
                    new_number = 1
                
                next_rmtr_no = f'{current_year}-{str(new_number).zfill(4)}'
            except Exception as e:
                logger.error(f"Error generating initial RMTR number: {str(e)}")
                next_rmtr_no = f'{current_year}-0001'

            context = {
                'rmtr_no': next_rmtr_no,
                'suppliers': Supplier.objects.all(),
                'plants': Plant.objects.all()
            }
            
            return render(request, 'test_request.html', context)
        
    except Exception as e:
        logger.error(f"Error in test_request view: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@require_http_methods(["GET"])
def generate_rmtr_number(request):
    """Generate next RMTR number"""
    try:
        current_year = timezone.now().year
        
        with transaction.atomic():  # Prevent race conditions
            last_entry = RMTRRequest.objects.filter(
                rmtr_no__iregex=f'^{current_year}-[0-9]{{4}}$'
            ).select_for_update().order_by('-rmtr_no').first()

            if last_entry:
                try:
                    year_part, number_part = last_entry.rmtr_no.split('-')
                    new_number = int(number_part) + 1
                except (ValueError, IndexError):
                    logger.error(f"Error parsing rmtr_no: {last_entry.rmtr_no}")
                    new_number = 1
            else:
                new_number = 1

            rmtr_number = f'{current_year}-{str(new_number).zfill(4)}'
            logger.info(f"Generated new RMTR number: {rmtr_number}")
            
            return JsonResponse({
                'status': 'success',
                'rmtr_number': rmtr_number
            })

    except Exception as e:
        logger.error(f"Error generating RMTR number: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Failed to generate RMTR number'
        }, status=500)
        
        
@api_view(['POST'])
def create_rmtr_request(request):
    if request.method == 'POST':
        form = RMTRRequestForm(request.POST, request.FILES)
        if form.is_valid():
            rmtr_request = form.save(commit=False)
            rmtr_request.rmtr_no = generate_rmtr_number()
            rmtr_request.save()
            return JsonResponse({
                'status': 'success',
                'redirect': '/dashboard/',  
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': form.errors.as_json(),
            }, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


def get_suppliers(request):
    suppliers = Supplier.objects.all().values('id', 'name')  # Query suppliers from the database
    return JsonResponse(list(suppliers), safe=False)


@api_view(['POST'])
def create_supplier(request):
    serializer = SupplierCreateSerializer(data=request.data)
    if serializer.is_valid():
        supplier = serializer.save()
        return Response(SupplierSerializer(supplier).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'POST'])
def manage_suppliers(request):
    if request.method == 'GET':
        suppliers = Supplier.objects.all()
        serializer = SupplierSerializer(suppliers, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        serializer = SupplierSerializer(data=request.data)
        if serializer.is_valid():
            supplier_id = serializer.validated_data.get('id')
            if supplier_id and Supplier.objects.filter(id=supplier_id).exists():
                return Response({"error": "Supplier with this ID already exists."}, status=status.HTTP_400_BAD_REQUEST)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



@login_required
def submit_form(request):
    try:
        if request.method != 'POST':
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid request method'
            }, status=405)

        form = RMTRRequestForm(request.POST, request.FILES)
        
        if not form.is_valid():
            return JsonResponse({
                'status': 'error',
                'message': 'Form validation failed',
                'errors': form.errors.as_json()
            }, status=400)

        # Create report instance
        with transaction.atomic():
            report = form.save(commit=False)
            
            # Get and validate supplier
            supplier_instance = form.cleaned_data.get('supplier')
            if not supplier_instance:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Supplier is required.'
                }, status=400)

            # Set report fields
            report.supplier = supplier_instance
            report.requested_by = form.cleaned_data.get('requested-by', request.user.username)
            report.status = 'pending'
            report.sub_category = form.cleaned_data.get('sub_category', '')
            report.approved_mgt = form.cleaned_data.get('approved-mgt')
            report.tests = request.POST.get('selected_tests', '')

            # Generate RMTR number if needed
            if not report.rmtr_no:
                report.rmtr_no = report.generate_next_rmtr_no()

            # Save the report
            report.save()
            logger.info(f"Created new RMTR: {report.rmtr_no}")

            # Send email notification
            try:
                send_mail(
                    subject='RMTR Report Submitted',
                    message=f'The RMTR report with number2 {report.rmtr_no} has been created on {report.date} by {report.requested_by}.',
                    from_email='kapaportal@kapa-oil.com',
                    recipient_list = [request.user.email, 'ict@kapa-oil.com'],

                    fail_silently=True
                )
            except Exception as e:
                logger.warning(f"Email notification failed for RMTR {report.rmtr_no}: {str(e)}")

            # Return success response
            return JsonResponse({
                'status': 'success',
                'message': 'RMTR created successfully',
                'rmtr_no': report.rmtr_no,
                'redirect': '/dashboard/'
            })

    except Exception as e:
        logger.error(f"Error in submit_form: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Server error occurred'
        }, status=500)


def fetch_material_data(request):
    # Query all materials, their subcategories, and tests
    materials = Material.objects.prefetch_related('subcategories__tests').all()

    # Prepare the response structure
    materials_data = []
    
    for material in materials:
        material_dict = {
            'material': material.name,
            'subcategories': []
        }
        
        for subcategory in material.subcategories.all():
            subcategory_dict = {
                'name': subcategory.name,
                'tests': [tests.name for tests in subcategory.tests.all()]  # List of tests for each subcategory
            }
            material_dict['subcategories'].append(subcategory_dict)
        
        materials_data.append(material_dict)

    return JsonResponse({'materials': materials_data})


def test(request):
    all_reports = RMTRRequest.objects.all()
    logger.info(all_reports)  # This will log all the report data in the console or log file
    return render(request, 'pending.html', {'pending_reports': all_reports})
  




logger = logging.getLogger(__name__)

@login_required
def pending_reports(request):
    all_reports = RMTRRequest.objects.all()
    return render(request, 'pending.html', {'pending_reports': all_reports})








logger = logging.getLogger(__name__)

def validate_image(image_file):
    """Validate uploaded image file"""
    if not image_file:
        return True, None

    # Check file size (5MB limit)
    if image_file.size > 5 * 1024 * 1024:
        return False, "Image file too large. Maximum size is 5MB."

    # Check file type
    allowed_types = ['image/jpeg', 'image/png', 'image/gif']
    file_type = mimetypes.guess_type(image_file.name)[0]
    if file_type not in allowed_types:
        return False, "Invalid file type. Please upload JPEG, PNG, or GIF."

    return True, None

def handle_image_upload(report, image_file):
    """Handle image upload and cleanup"""
    try:
        # Remove old image if exists
        if report.test_image:
            try:
                old_path = report.test_image.path
                if os.path.exists(old_path):
                    os.remove(old_path)
            except Exception as e:
                logger.warning(f"Error removing old image for RMTR {report.rmtr_no}: {str(e)}")

        # Rename new image
        ext = os.path.splitext(image_file.name)[1]
        image_file.name = f"{report.rmtr_no}_test_image{ext}"
        report.test_image = image_file
        return True, None

    except Exception as e:
        logger.error(f"Error handling image upload: {str(e)}")
        return False, "Error processing uploaded image"

def send_notification_email(report, test_count, test_data):
    """Send email notification about completed tests"""
    try:
        tests_summary = "\n".join([
            f"• {test['test']}"
            f"\n  - Sample Results: {test['sample']}"
            f"\n  - Raw Material Results: {test['raw_material']}"
            f"\n  - Kapa Standards: {test['standards']}"
            for test in test_data
        ])

        message = f"""
RMTR Test Results Completion Notice

RMTR Number: {report.rmtr_no}
Tests Completed: {test_count}
Performed By: {report.tests_done_by}

Test Results Summary:
{tests_summary}

Lab QC Comments:
{report.lab_qc_comments}

Please review the results at your earliest convenience.
        """

        send_mail(
            subject=f'RMTR {report.rmtr_no} - Lab Tests Completed ({test_count} tests)',
            message=message,
            from_email='kapaportal@kapa-oil.local',
            recipient_list=[report.requested_by.email, 'ict@kapa-oil.com'],
            fail_silently=True
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to send email notification: {str(e)}")
        return False
    



@login_required
def fill_page(request, rmtr_no):
    """Handle RMTR test results form"""
    try:
        # Get RMTR request
        report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)
        
        # Check permissions
        if not request.user.groups.filter(name__in=['LAB', 'ADMIN']).exists():
            messages.error(request, 'You do not have permission to access this page')
            return redirect('pending')

        # Handle form submission
        
        if request.method == 'POST':
            try:
                # Validate required fields
                lab_qc_comments = request.POST.get('lab_qc_comments', '').strip()
                tests_done_by = request.POST.get('tests_done_by', '').strip()

                if not lab_qc_comments:
                    return JsonResponse({
                        'success': False,
                        'message': 'Please provide lab QC comments'
                    }, status=400)

                if not tests_done_by:
                    return JsonResponse({
                        'success': False,
                        'message': 'Please specify who performed the tests'
                    }, status=400)

                # Process test data
                test_data = []
                test_count = 0

                # Collect and validate test data
                for i in range(1, 17):
                    test_name = request.POST.get(f'tests_carried_out{i}', '').strip()
                    if test_name:
                        test_info = {
                            'index': i,
                            'test': test_name,
                            'sample': request.POST.get(f'sample_results{i}', '').strip(),
                            'raw_material': request.POST.get(f'raw_material_results{i}', '').strip(),
                            'standards': request.POST.get(f'kapa_standards{i}', '').strip()
                        }
                        
                        # Validate test data completeness
                        if not all([test_info['sample'], test_info['raw_material'], test_info['standards']]):
                            return JsonResponse({
                                'success': False,
                                'message': f'Incomplete data for test "{test_name}". All fields are required.'
                            }, status=400)
                            
                        test_data.append(test_info)
                        test_count += 1

                if test_count == 0:
                    return JsonResponse({
                        'success': False,
                        'message': 'At least one test result is required'
                    }, status=400)

                # Validate image when uploaded
                if 'test_image' in request.FILES:
                    is_valid, error = validate_image(request.FILES['test_image'])
                    if not is_valid:
                        return JsonResponse({
                            'success': False,
                            'message': error
                        }, status=400)

                # Save all data
                try:
                    # Clear existing test data
                    for i in range(1, 17):
                        setattr(report, f'tests_carried_out{i}', '')
                        setattr(report, f'sample_results{i}', '')
                        setattr(report, f'raw_material_results{i}', '')
                        setattr(report, f'kapa_standards{i}', '')

                    # Save new test data
                    for test in test_data:
                        i = test['index']
                        setattr(report, f'tests_carried_out{i}', test['test'])
                        setattr(report, f'sample_results{i}', test['sample'])
                        setattr(report, f'raw_material_results{i}', test['raw_material'])
                        setattr(report, f'kapa_standards{i}', test['standards'])
                        logger.debug(f"Saved test {i}: {test['test']}")

                    # Save other fields
                    report.lab_qc_comments = lab_qc_comments
                    report.tests_done_by = tests_done_by

                    # Handle image upload
                    if 'test_image' in request.FILES:
                        success, error = handle_image_upload(report, request.FILES['test_image'])
                        if not success:
                            return JsonResponse({
                                'success': False,
                                'message': error
                            }, status=400)

                    # Update status and save
                    report.status = 'Pending QAO review'
                    report.save()

                    # HTML email Tabel
                    html_message = f"""
                    <html>
                    <head>
                        <style>
                            body {{
                                font-family: Arial, sans-serif;
                                max-width: 780px;
                                margin: 0 auto;
                            }}
                            table {{
                                border-collapse: collapse;
                                width: 80%;
                                margin-bottom: 15px;
                                margin-left: auto;
                                margin-right: auto;
                            }}
                            th, td {{
                                border: 1px solid #ddd;
                                padding: 5px 8px;
                                text-align: left;
                                font-size: 14px;
                            }}
                            th {{
                                background-color: #f2f2f2;
                                font-weight: bold;
                            }}
                            tr:nth-child(even) {{
                                background-color: #f9f9f9;
                            }}
                            .header-table {{
                                width: 65%;
                                margin-bottom: 20px;
                            }}
                            .section-title {{
                                font-weight: bold;
                                font-size: 16px;
                                margin-top: 15px;
                                margin-bottom: 5px;
                                text-align: left;
                                padding-left: 7.5%;
                            }}
                        </style>
                    </head>
                    <body>
                        <h2 style="text-align: center;">Lab Test Results for RMTR NO: {report.rmtr_no}</h2>
                        <table class="header-table">
                            <tr>
                                <th>Number of Tests</th>
                                <td>{test_count}</td>
                            </tr>
                            <tr>
                                <th>Tests Performed By</th>
                                <td>{tests_done_by}</td>
                            </tr>
                            <tr>
                                <th>Submission Date</th>
                                <td>{timezone.now().strftime("%Y-%m-%d %H:%M:%S")}</td>
                            </tr>
                            <tr>
                                <th>Action By</th>
                                <td>{request.user.get_full_name() or request.user.username}</td>
                            </tr>
                        </table>

                        <div class="section-title">Lab QC Comments:</div>
                        <table>
                            <tr>
                                <td>{lab_qc_comments}</td>
                            </tr>
                        </table>

                        <div class="section-title">Test Results:</div>
                        <table>
                            <tr>
                                <th>Test</th>
                                <th>Sample Results</th>
                                <th>Current Raw Material Results</th>
                                <th>KAPA Standards</th>
                            </tr>
                    """

                    # Add test results as row in the table
                    for test in test_data:
                        html_message += f"""
                            <tr>
                                <td>{test['test']}</td>
                                <td>{test['sample']}</td>
                                <td>{test['raw_material']}</td>
                                <td>{test['standards']}</td>
                            </tr>
                        """

                    # Close the HTML
                    html_message += f"""
                        </table>
                        <p>Raw Material Test Report Link: <a href="http://10.0.0.7:8020">http://10.0.0.7:8020</a></p>
                    </body>
                    </html>
                    """

                    # Plain text
                    plain_message = f"""
Lab test results for RMTR NO: {report.rmtr_no}

Number of Tests: {test_count}
Tests Performed By: {tests_done_by}
Submission Date: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}

Lab QC Comments:
{lab_qc_comments}

Test Results:
"""
                    for test in test_data:
                        plain_message += f"""
Test: {test['test']}
Sample Results: {test['sample']}
Current Raw Material Results: {test['raw_material']}
KAPA Standards: {test['standards']}
---------------------------"""

                    plain_message += f"""

Action By: {request.user.get_full_name() or request.user.username}

Raw Material Test Report Link: http://10.0.0.7:8020
"""
                    
                    recipients = [
                        'ict@kapa-oil.com',
                        'qao.user6@kapa-oil.com',
                        'qao.user47@kapa-oil.com',
                        request.user.email  
    
                    ]

                    # Subject
                    subject = f'Lab Test Results - RMTR {report.rmtr_no}'

                    try:
                        # HTML email with fallback to plain text
                        from django.core.mail import EmailMultiAlternatives
                        
                        email = EmailMultiAlternatives(
                            subject=subject,
                            body=plain_message,
                            from_email='kapaportal@kapa-oil.local',
                            to=recipients
                        )
                        email.attach_alternative(html_message, "text/html")
                        email.send(fail_silently=True)
                        
                    except Exception as e:
                        logger.error(f"Error sending email: {str(e)}")
                        # Fall back to plain text email if HTML email fails
                        try:
                            send_mail(
                                subject=subject,
                                message=plain_message,
                                from_email='kapaportal@kapa-oil.local',
                                recipient_list=recipients,
                                fail_silently=True,
                            )
                        except Exception as e:
                            logger.error(f"Error sending fallback email: {str(e)}")

                    return JsonResponse({
                        'success': True,
                        'message': f'Successfully saved {test_count} test results'
                    })

                except Exception as e:
                    logger.error(f"Error saving data: {str(e)}")
                    return JsonResponse({
                        'success': False,
                        'message': 'Error saving data to database'
                    }, status=500)

            except Exception as e:
                logger.error(f"Error processing form submission: {str(e)}")
                return JsonResponse({
                    'success': False,
                    'message': f'Error processing form submission: {str(e)}'
                }, status=500)

        # Handle GET request
        context = {
            'form_data': report,
            'page_title': 'Lab Test Results Form',
            'can_edit': report.status in ['hod_approved', 'pending']
        }
        
        return render(request, 'fill_page.html', context)

    except Exception as e:
        logger.error(f"Error in fill_page view: {str(e)}")
        messages.error(request, 'Error accessing the test form')
        return redirect('pending')
    


    

@login_required
def final_report(request):
    report = get_object_or_404(RawMaterialTestReport)

    if request.method == 'POST':
        html_string = render_to_string('pdf_report.html')
        pdf_file = HTML(string=html_string).write_pdf()
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="test_report.pdf"'
        return response

    return render(request, 'pdf_report.html', {'report': report})




@login_required
def approval_page(request):
    report = get_object_or_404(RawMaterialTestReport)

    if request.method == 'POST':
        if 'approve' in request.POST:
            report.final_conclusion = "Approved"
            messages.success(request, 'Report approved successfully.')
        elif 'reject' in request.POST:
            report.final_conclusion = "Rejected"
            messages.error(request, 'Report rejected.')
        
        report.save()
        return redirect('pdf_report')

    return render(request, 'approval_page.html')



@login_required
def check_pending_rmtrs(request):
    """API endpoint to check for new pending RMTRs."""
    try:
        user_groups = [group.name for group in request.user.groups.all()]
        
        pending_rmtrs = RMTRRequest.objects.filter(
            status__in=[
                status for status, config in STATUS_FLOW.items()
                if config['group'] in user_groups
            ]
        ).values('rmtr_no', 'status', 'date_created')

        return JsonResponse({
            'pending_rmtrs': list(pending_rmtrs),
            'count': len(pending_rmtrs)
        })

    except Exception as e:
        logger.error(f"Error checking pending RMTRs: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Failed to check pending RMTRs'}, status=500)
    
    
    



logger = logging.getLogger(__name__)
STATUS_CONFIG = {
    'report_created': {
        'display': 'Pending: HOD Purchase Approval',
        'next': 'hod_purchase_approval',
        'group': 'HOD_PURCHASE',
        'route': 'hod_purchase_approval'
    },
    'hod_purchase_approved': {
        'display': 'Pending: Management 1st Approval',
        'next': 'management_approval',
        'group': 'MANAGEMENT',
        'route': 'management_approval'
    },
    'management_approved': {
        'display': 'Pending: Management 2nd Approval',
        'next': 'management_approval_2',
        'group': 'MANAGEMENT',
        'route': 'management_approval_2'
    },
    'management_approved_2': {
        'display': 'Pending: FM Approval',
        'next': 'fm_approval',
        'group': 'FM',
        'route': 'fm_approval'
    },
    'fm_approved': {
        'display': 'Pending: HOD Approval',
        'next': 'hod_approval',
        'group': 'HOD',
        'route': 'hod_approval'
    },
    'hod_approved': {
        'display': 'Pending: Lab Test',
        'next': 'fill_page',
        'group': 'LAB',
        'route': 'fill_page'
    },
    'test_completed': {
        'display': 'Pending: QAO Review',
        'next': 'qao_test_approval',
        'group': 'QAO',
        'route': 'qao_test_approval'
    },
    'qao_reviewed': {
        'display': 'Pending: HOD Test Approval',
        'next': 'hod_test_approval',
        'group': 'HOD_TEST',
        'route': 'hod_test_approval'
    },
    'hod_test_approved': {
        'display': 'Pending: FM Test Approval',
        'next': 'fm_test_approval',
        'group': 'FM_TEST',
        'route': 'fm_test_approval'
    },
    'fm_test_approved': {
        'display': 'Pending: Management Test Approval',
        'next': 'management_test_approval',
        'group': 'MANAGEMENT_TEST',
        'route': 'management_test_approval'
    },
    'management_test_approved': {
        'display': 'Pending: Milan Approval',
        'next': 'milan_approval',
        'group': 'MILAN',
        'route': 'milan_approval'
    },
    'milan_approval': {
        'display': 'Under Final Review',
        'next': 'completed',
        'group': 'MILAN',
        'route': 'milan_approval'
    },
    'completed': {
        'display': 'Completed',
        'next': None,
        'group': 'ADMIN',
        'route': None
    },
    'rejected': {
        'display': 'Rejected',
        'next': None,
        'group': 'ADMIN',
        'route': None
    }
}
STATUS_MAPPING = {
    'report_created': 'Pending: HOD Purchase approval',
    'hod_purchase_approved': 'Pending: Management approval',
    'management_approved': 'Pending: Management approval 2',
    'management_approved_2': 'Pending: FM approval',
    'hod_approved': 'Test in progress',
    'pending_retest': 'Pending retest',
    'retesting': 'Test in progress',
    'test_completed': 'Pending: QAO approval',
    'hod_test_approved': 'Pending: FM Test approval',
    'fm_test_approved': 'Pending: Management Test approval',
    'management_test_approved': 'Pending: Milan approval',
    'completed': 'Completed'
}
@login_required
def my_rmtr(request):
    """View for displaying RMTRs with special handling for ADMIN users and department-specific access."""
    try:
        user = request.user
        user_groups = [group.name for group in user.groups.all()]
        is_admin = 'ADMIN' in user_groups

        if not user_groups:
            messages.error(request, 'You do not have any assigned roles. Please contact your administrator.')
            return redirect('login')

        # Define department mapping
        DEPARTMENT_GROUPS = {
            'HOD_BAKING': 'BAKING',
            'HOD_REFINERY': 'REFINERY',
            'HOD_TISSUE': 'TISSUE',
            'HOD_SOAP': 'SOAP',
            'HOD_DETERGENT': 'DETERGENT',
            'HOD_MATCHBOX': 'MATCHBOX',
            'HOD_NOODLES': 'NOODLES',
            'HOD_TEST_BAKING': 'BAKING',
            'HOD_TEST_REFINERY': 'REFINERY',
            'HOD_TEST_TISSUE': 'TISSUE',
            'HOD_TEST_SOAP': 'SOAP',
            'HOD_TEST_DETERGENT': 'DETERGENT',
            'HOD_TEST_MATCHBOX': 'MATCHBOX',
            'HOD_TEST_NOODLES': 'NOODLES'
        }

        # Define status mapping - these are the ONLY statuses each group should see
        GROUP_STATUS_MAP = {
            'HOD_PURCHASE': ['report_created'],
            'MANAGEMENT': ['hod_purchase_approved', 'management_approved'],
            'FM': ['management_approved_2'],
            'LAB': ['hod_approved', 'pending_retest', 'retesting'],
            'QAO': ['test_completed'],
            'FM_TEST': ['hod_test_approved'],
            'MANAGEMENT_TEST': ['fm_test_approved'],
            'MILAN': ['management_test_approved']
        }

        # Special handling for ADMIN
        if is_admin:
            # Get all RMTRs
            rmtrs_query = RMTRRequest.objects.all()

            # Handle status filter for admin
            status_filter = request.GET.get('status')
            if status_filter and status_filter != 'all':
                rmtrs_query = rmtrs_query.filter(status=status_filter)

            # Handle department filter for admin
            dept_filter = request.GET.get('department')
            if dept_filter and dept_filter != 'all':
                rmtrs_query = rmtrs_query.filter(plant=dept_filter)

            # Handle search
            search_query = request.GET.get('search')
            if search_query:
                rmtrs_query = rmtrs_query.filter(
                    Q(rmtr_no__icontains=search_query) |
                    Q(supplier__icontains=search_query) |
                    Q(material_type__icontains=search_query) |
                    Q(plant__icontains=search_query) |
                    Q(status__icontains=search_query) |
                    Q(requested_by__username__icontains=search_query)
                )

            # Handle sorting
            sort_field = request.GET.get('sort', '-date_created')
            rmtrs_query = rmtrs_query.order_by(sort_field)

            # Pagination
            paginator = Paginator(rmtrs_query, 50)
            page = request.GET.get('page', 1)
            rmtrs = paginator.get_page(page)

            context = {
                'rmtrs': rmtrs,
                'is_admin': True,
                'user_groups': user_groups,
                'status_options': STATUS_CONFIG.keys(),
                'department_options': ['BAKING', 'REFINERY', 'TISSUE', 'SOAP', 
                                    'DETERGENT', 'MATCHBOX', 'NOODLES'],
                'total_count': RMTRRequest.objects.count(),
                'status_counts': {
                    status: RMTRRequest.objects.filter(status=status).count()
                    for status in STATUS_CONFIG.keys()
                },
                'department_counts': {
                    dept: RMTRRequest.objects.filter(plant=dept).count()
                    for dept in ['BAKING', 'REFINERY', 'TISSUE', 'SOAP', 
                               'DETERGENT', 'MATCHBOX', 'NOODLES']
                },
                'search_query': search_query,
                'current_sort': sort_field,
                'current_status_filter': status_filter,
                'current_dept_filter': dept_filter,
                'status_config': STATUS_CONFIG,
                'status_mapping': STATUS_MAPPING
            }

            return render(request, 'my_rmtr.html', context)

        # Handle regular users and department-specific users, quer filter
    
        pending_filter = Q()
        
    
        user_departments = [DEPARTMENT_GROUPS[group] for group in user_groups if group in DEPARTMENT_GROUPS]

      
        for group in user_groups:
     
            if group == 'ADMIN':
                continue
                
            base_group = group
            department = None

            # Handle department-specific groups (HOD groups)
            if group in DEPARTMENT_GROUPS:
                department = DEPARTMENT_GROUPS[group]
           
                if group.startswith('HOD_'):
                    base_group = 'HOD_PURCHASE'
                elif group.startswith('HOD_TEST_'):
                    base_group = group[:group.rindex('_')]

        
            if base_group in GROUP_STATUS_MAP:
                statuses = GROUP_STATUS_MAP[base_group]
                if not isinstance(statuses, list):
                    statuses = [statuses]

               
                if department:
                    for status in statuses:
                        pending_filter |= Q(status=status, plant=department)
                else:
                    
                    pending_filter |= Q(status__in=statuses)

        # Get RMTRs based on constructed filter
        pending_rmtrs = RMTRRequest.objects.filter(pending_filter)

        # Handle search
        search_query = request.GET.get('search')
        if search_query:
            pending_rmtrs = pending_rmtrs.filter(
                Q(rmtr_no__icontains=search_query) |
                Q(supplier__icontains=search_query) |
                Q(material_type__icontains=search_query) |
                Q(plant__icontains=search_query) |
                Q(requested_by__username__icontains=search_query)
            )

        # Handle sorting
        sort_field = request.GET.get('sort', '-date_created')
        pending_rmtrs = pending_rmtrs.order_by(sort_field)

        # Pagination
        paginator = Paginator(pending_rmtrs, 50)
        page = request.GET.get('page', 1)
        rmtrs = paginator.get_page(page)

        context = {
            'rmtrs': rmtrs,
            'is_admin': False,
            'user_groups': user_groups,
            'user_departments': user_departments,
            'pending_count': pending_rmtrs.count(),
            'search_query': search_query,
            'current_sort': sort_field,
            'status_config': STATUS_CONFIG,
            'status_mapping': STATUS_MAPPING,
            'department_specific': bool(user_departments),
            'allowed_departments': user_departments
        }

        return render(request, 'my_rmtr.html', context)

    except Exception as e:
        logger.error(f"Error in my_rmtr view: {str(e)}", exc_info=True)
        messages.error(request, 'An error occurred while loading your RMTRs.')
        return redirect('dashboard')

@login_required
def get_target_route(request):
    """API endpoint to get the target route for a given status and user groups."""
    try:
        status = request.GET.get('status', '').lower()
        user_groups = request.GET.get('user_groups', '').split(',')

        status_config = ROUTE_MAPPING.get(status)
        if status_config and status_config['group'] in user_groups:
            return JsonResponse({
                'targetRoute': status_config['route'],
                'status': 'success',
                'description': status_config['description'],
                'next_description': status_config['next_description'],
                'step': status_config['step']
            })

        return JsonResponse({
            'status': 'error',
            'message': 'No route found for given status and user groups'
        })

    except Exception as e:
        logger.error(f"Error in get_target_route: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'An error occurred'
        }, status=500)
def get_rmtr_details(request, rmtr_no):
    """
    API endpoint to get RMTR details for the modal
    """
    try:
        rmtr = RMTRRequest.objects.get(rmtr_no=rmtr_no)
        data = {
            'rmtr_no': rmtr.rmtr_no,
            'supplier': {
                'name': rmtr.supplier.name if rmtr.supplier else None,
            },
            'material_type': rmtr.material_type,
            'plant': {
                'name': rmtr.plant.name if rmtr.plant else None,
            },
            'status': rmtr.status,
            'date_created': rmtr.date_created.isoformat() if rmtr.date_created else None,
            # Add any other fields you want to display in the modal
        }
        return JsonResponse(data)
    except RMTRRequest.DoesNotExist:
        return JsonResponse({'error': 'RMTR not found'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching RMTR details: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Internal server error'}, status=500)
    
STATUS_CONFIG = {
    'report_created': {
        'display': 'Pending: HOD Purchase Approval',
        'next': 'hod_purchase_approval',
        'group': 'HOD_PURCHASE',
        'route': 'hod_purchase_approval'
    },
    'hod_purchase_approved': {
        'display': 'Pending: Management 1st Approval',
        'next': 'management_approval',
        'group': 'MANAGEMENT',
        'route': 'management_approval'
    },
    'management_approved': {
        'display': 'Pending: Management 2nd Approval',
        'next': 'management_approval_2',
        'group': 'MANAGEMENT',
        'route': 'management_approval_2'
    },
    'management_approved_2': {
        'display': 'Pending: FM Approval',
        'next': 'fm_approval',
        'group': 'FM',
        'route': 'fm_approval'
    },
    'fm_approved': {
        'display': 'Pending: HOD Approval',
        'next': 'hod_approval',
        'group': 'HOD',
        'route': 'hod_approval'
    },
    'hod_approved': {
        'display': 'Pending: Lab Test',
        'next': 'fill_page',
        'group': 'LAB',
        'route': 'fill_page'
    },
    'test_completed': {
        'display': 'Pending: QAO Review',
        'next': 'qao_test_approval',
        'group': 'QAO',
        'route': 'qao_test_approval'
    },
    'qao_reviewed': {
        'display': 'Pending: HOD Test Approval',
        'next': 'hod_test_approval',
        'group': 'HOD_TEST',
        'route': 'hod_test_approval'
    },
    'hod_test_approved': {
        'display': 'Pending: FM Test Approval',
        'next': 'fm_test_approval',
        'group': 'FM_TEST',
        'route': 'fm_test_approval'
    },
    'fm_test_approved': {
        'display': 'Pending: Management Test Approval',
        'next': 'management_test_approval',
        'group': 'MANAGEMENT_TEST',
        'route': 'management_test_approval'
    },
    'management_test_approved': {
        'display': 'Pending: Milan Approval',
        'next': 'milan_approval',
        'group': 'MILAN',
        'route': 'milan_approval'
    },
    'milan_approval': {
        'display': 'Under Final Review',
        'next': 'completed',
        'group': 'MILAN',
        'route': 'milan_approval'
    },
    'completed': {
        'display': 'Completed',
        'next': None,
        'group': 'ADMIN',
        'route': None
    },
    'rejected': {
        'display': 'Rejected',
        'next': None,
        'group': 'ADMIN',
        'route': None
    }
}  



@login_required
def all_rmtr(request):
    try:
        user_groups = list(request.user.groups.values_list('name', flat=True))
        logger.info(f"User groups for {request.user.username}: {user_groups}")

        if not user_groups:
            messages.error(request, 'You do not have any assigned roles. Please contact your administrator.')
            return redirect('login')

        # Get all RMTRs without status filtering
        reports = RMTRRequest.objects.all().select_related('supplier', 'plant')

        # Custom ordering by RMTR number
        reports = sorted(
            reports,
            key=lambda x: (
                -int(x.rmtr_no.split('-')[0]), 
                -int(x.rmtr_no.split('-')[1])   
            )
        )

        # Process each report for display
        processed_reports = []
        for report in reports:
            normalized_status = normalize_status(report.status)
            report.internal_status = normalized_status

            # Set display status using the mapping
            config = STATUS_CONFIG.get(normalized_status, {})
            report.display_status = config.get('display', report.status)

            # Add retest capabilities
            report.can_retest = config.get('can_retest', False)
            if report.can_retest:
                report.retest_chain = config.get('retest_chain', [])
                report.user_can_retest = any(group in report.retest_chain for group in user_groups)
            else:
                report.user_can_retest = False

            # Add approval/rejection capabilities
            report.can_approve = config.get('can_approve', False)
            report.can_reject = config.get('can_reject', False)

            # Add user permissions based on groups
            report.user_can_edit = any(group in config.get('edit_groups', []) for group in user_groups)
            report.user_can_view = any(group in config.get('view_groups', []) for group in user_groups)
            report.user_can_approve = any(group in config.get('approve_groups', []) for group in user_groups)
            report.user_can_reject = any(group in config.get('reject_groups', []) for group in user_groups)

            processed_reports.append(report)

        # Apply search if provided
        search_query = request.GET.get('search')
        if search_query:
            search_query = search_query.lower()
            processed_reports = [
                report for report in processed_reports
                if search_query in report.rmtr_no.lower() or
                   search_query in report.supplier.name.lower() or
                   search_query in report.material_type.lower() or
                   search_query in report.plant.name.lower() or
                   search_query in str(report.status).lower() or
                   search_query in str(report.material_name).lower()
            ]

        # Handle sorting
        sort_field = request.GET.get('sort')
        if sort_field:
            reverse_sort = False
            if sort_field.startswith('-'):
                reverse_sort = True
                sort_field = sort_field[1:]
            
            processed_reports = sorted(
                processed_reports,
                key=lambda x: getattr(x, sort_field, ''),
                reverse=reverse_sort
            )

        # Prepare status filters
        all_statuses = set(report.status for report in processed_reports)
        status_filters = sorted(list(all_statuses))

        # Get current active filters
        active_filters = request.GET.getlist('status_filter')

        # Calculate statistics
        total_reports = len(processed_reports)
        completed_reports = len([r for r in processed_reports if r.status.lower() == 'completed'])
        pending_reports = len([r for r in processed_reports if r.status.lower() != 'completed' and r.status.lower() != 'rejected'])
        rejected_reports = len([r for r in processed_reports if r.status.lower() == 'rejected'])

        # REMOVE SERVER-SIDE PAGINATION - Send all reports to the frontend
        # Let JavaScript handle pagination

        context = {
            'pending_reports': processed_reports,  # Send ALL reports, not just a page
            'user_groups': user_groups,
            'search_query': search_query,
            'status_config': STATUS_CONFIG,
            'status_display_mapping': STATUS_DISPLAY_MAPPING,
            'status_filters': status_filters,
            'active_filters': active_filters,
            'statistics': {
                'total': total_reports,
                'completed': completed_reports,
                'pending': pending_reports,
                'rejected': rejected_reports,
            },
            'current_sort': sort_field if sort_field else '',
            'show_filters': True,
            'show_statistics': True,
            'show_all_reports': True  
        }

        return render(request, 'all_rmtr.html', context)

    except Exception as e:
        logger.exception(f"Error in all_rmtr view: {str(e)}")
        messages.error(request, 'An error occurred while loading the dashboard.')
        return redirect('dashboard')


STATUS_CONFIG = {
    'report_created': {
        'display': 'Pending: HOD Purchase Approval',
        'next': 'hod_purchase_approval',
        'group': 'HOD_PURCHASE',
        'route': 'hod_purchase_approval'
    },
    'hod_purchase_approved': {
        'display': 'Pending: Management 1st Approval',
        'next': 'management_approval',
        'group': 'MANAGEMENT',
        'route': 'management_approval'
    },
    'management_approved': {
        'display': 'Pending: Management 2nd Approval',
        'next': 'management_approval_2',
        'group': 'MANAGEMENT',
        'route': 'management_approval_2'
    },
    'management_approved_2': {
        'display': 'Pending: FM Approval',
        'next': 'fm_approval',
        'group': 'FM',
        'route': 'fm_approval'
    },
    'fm_approved': {
        'display': 'Pending: HOD Approval',
        'next': 'hod_approval',
        'group': 'HOD',
        'route': 'hod_approval'
    },
    'hod_approved': {
        'display': 'Pending: Lab Test',
        'next': 'fill_page',
        'group': 'LAB',
        'route': 'fill_page'
    },
    'test_completed': {
        'display': 'Pending: QAO Review',
        'next': 'qao_test_approval',
        'group': 'QAO',
        'route': 'qao_test_approval'
    },
    'qao_reviewed': {
        'display': 'Pending: HOD Test Approval',
        'next': 'hod_test_approval',
        'group': 'HOD_TEST',
        'route': 'hod_test_approval'
    },
    'hod_test_approved': {
        'display': 'Pending: FM Test Approval',
        'next': 'fm_test_approval',
        'group': 'FM_TEST',
        'route': 'fm_test_approval'
    },
    'fm_test_approved': {
        'display': 'Pending: Management Test Approval',
        'next': 'management_test_approval',
        'group': 'MANAGEMENT_TEST',
        'route': 'management_test_approval'
    },
    'management_test_approved': {
        'display': 'Pending: Milan Approval',
        'next': 'milan_approval',
        'group': 'MILAN',
        'route': 'milan_approval'
    },
    'milan_approval': {
        'display': 'Under Final Review',
        'next': 'completed',
        'group': 'MILAN',
        'route': 'milan_approval'
    },
    'completed': {
        'display': 'Completed',
        'next': None,
        'group': 'ADMIN',
        'route': None
    },
    'rejected': {
        'display': 'Rejected',
        'next': None,
        'group': 'ADMIN',
        'route': None
    }
}
STATUS_GROUP_MAP = {
            'HOD_PURCHASE': ['report_created'],
            'MANAGEMENT': ['hod_purchase_approved', 'management_approved'],
            'FM': ['management_approved_2'],
            'LAB': ['hod_approved', 'pending_retest', 'retesting'],
            'QAO': ['test_completed'],
            'FM_TEST': ['hod_test_approved'],
            'MANAGEMENT_TEST': ['fm_test_approved'],
            'MILAN': ['management_test_approved']
        }

@login_required
def dashboard(request):
    try:
        user = request.user
        user_groups = [group.name for group in user.groups.all()]
        is_admin = 'ADMIN' in user_groups

        # Get all plant objects first
        plants = Plant.objects.all()
        plant_mapping = {plant.name: plant.id for plant in plants}

        # Initialize context
        context = {
            'user_groups': user_groups,
            'is_admin': is_admin
        }

        # Define department mapping
        DEPARTMENT_GROUPS = {
            'HOD_BAKING': plant_mapping.get('BAKING'),
            'HOD_REFINERY': plant_mapping.get('REFINERY'),
            'HOD_TISSUE': plant_mapping.get('TISSUE'),
            'HOD_SOAP': plant_mapping.get('SOAP'),
            'HOD_DETERGENT': plant_mapping.get('DETERGENT'),
            'HOD_MATCHBOX': plant_mapping.get('MATCHBOX'),
            'HOD_NOODLES': plant_mapping.get('NOODLES'),
            'HOD_TEST_BAKING': plant_mapping.get('BAKING'),
            'HOD_TEST_REFINERY': plant_mapping.get('REFINERY'),
            'HOD_TEST_TISSUE': plant_mapping.get('TISSUE'),
            'HOD_TEST_SOAP': plant_mapping.get('SOAP'),
            'HOD_TEST_DETERGENT': plant_mapping.get('DETERGENT'),
            'HOD_TEST_MATCHBOX': plant_mapping.get('MATCHBOX'),
            'HOD_TEST_NOODLES': plant_mapping.get('NOODLES')
        }

        # Special handling for ADMIN
        if is_admin:
            base_query = RMTRRequest.objects.all()
            context.update({
                'all_rmtr': base_query.count(),
                'pending_count': base_query.exclude(
                    status__in=['completed', 'rejected']
                ).count(),
                'completed_count': base_query.filter(
                    status='completed'
                ).count(),
                'rejected_count': base_query.filter(
                    status='rejected'
                ).count(),
                'my_works': base_query.count(),
                'department_stats': {
                    plant.name: RMTRRequest.objects.filter(plant=plant).count()
                    for plant in plants
                },
                'status_stats': {
                    status: RMTRRequest.objects.filter(status=status).count()
                    for status in STATUS_CONFIG.keys()
                },
                'retest_stats': {
                    'pending': RMTRRequest.objects.filter(status='pending_retest').count(),
                    'in_progress': RMTRRequest.objects.filter(status='retesting').count(),
                    'completed': RMTRRequest.objects.filter(status='retest_completed').count()
                }
            })
        
        # Handle regular users (no groups)
        elif not user_groups:
            base_query = RMTRRequest.objects.filter(requested_by=user)
            context.update({
                'all_rmtr': base_query.exclude(
                    status__in=['completed', 'rejected']
                ).count(),
                'pending_count': base_query.filter(
                    status='report_created'
                ).count(),
                'completed_count': base_query.filter(
                    status__in=['completed', 'rejected']
                ).count(),
                'my_works': base_query.exclude(
                    status__in=['completed', 'rejected']
                ).count()
            })

        # Handle all other groups (including HODs, FM, LAB, etc.)
        else:
            base_query = RMTRRequest.objects
            department_ids = set()

            # Collect all relevant department IDs
            for group in user_groups:
                if group in DEPARTMENT_GROUPS and DEPARTMENT_GROUPS[group] is not None:
                    department_ids.add(DEPARTMENT_GROUPS[group])

            # Filter by departments if user has department access
            if department_ids:
                base_query = base_query.filter(plant_id__in=department_ids)

            # Default status handling for non-mapped groups
            pending_query = base_query.exclude(status__in=['completed', 'rejected'])
            completed_query = base_query.filter(status__in=['completed', 'rejected'])
            
            # Calculate counts
            pending_count = pending_query.count()
            completed_count = completed_query.count()
            my_works_count = pending_query.count()
            all_rmtr_count = pending_count + completed_count

            # Get department names if applicable
            user_department_names = []
            if department_ids:
                user_department_names = [
                    plants.get(id=dept_id).name 
                    for dept_id in department_ids
                ]

            # Update context
            context.update({
                'all_rmtr': all_rmtr_count,
                'pending_count': pending_count,
                'completed_count': completed_count,
                'my_works': my_works_count
            })

            if user_department_names:
                context['user_departments'] = user_department_names

        return render(request, 'dashboard.html', context)

    except Exception as e:
        logger.error(f"Error in dashboard view: {str(e)}", exc_info=True)
        messages.error(request, 'An error occurred while loading the dashboard.')
        return redirect('login')

@login_required
def get_rmtr_report_data(request, rmtr_no):
    """API endpoint to get report data for PDF generation"""
    try:
        report = RMTRRequest.objects.select_related(
            'supplier', 
            'plant'
        ).get(rmtr_no=rmtr_no)

        report_data = {
            'material_type': report.material_type,
            'sub_category': report.sub_category,
            'tests_carried_out': report.tests,
            'raw_material_results': _format_results(report.raw_material_results),
            'kapa_standards': _format_standards(report.specs),
            'sample_results': _format_results(report.sample_results),
            'supplier': report.supplier.name if report.supplier else 'N/A',
            'plant': report.plant.name if report.plant else 'N/A',
            'qao_comments': report.qao_comments if hasattr(report, 'qao_comments') else '',
            'management_test_date_approved': report.management_test_date_approved.strftime('%Y-%m-%d') if report.management_test_date_approved else 'N/A'
        }

        return JsonResponse(report_data)

    except ObjectDoesNotExist:
        return JsonResponse({
            'error': f'Report with RMTR number {rmtr_no} not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error fetching report data: {str(e)}")
        return JsonResponse({
            'error': 'Error fetching report data'
        }, status=500)
    





STATUS_CONFIG = {
    'report_created': {
        'display': 'Pending: HOD Purchase Approval',
        'next_stage': 'hod_purchase_approved',
        'group': 'HOD_PURCHASE, PURCHASE',
        'can_retest': False
    },
    'hod_purchase_approved': {
        'display': 'Pending: Management Approval',
        'next_stage': 'management_approved',
        'group': 'HOD_PURCHASE',
        'can_retest': False
    },
    'management_approved': {
        'display': 'Pending: Management 2nd Approval',
        'next_stage': 'management_approved_2',
        'group': 'MANAGEMENT',
        'can_retest': False,
        'check_second_approver': True
    },
    
    #'management_approved_2': {
        #'display': 'Pending: HOD Approval',
        #'next_stage': 'hod_approved',
        #'group': 'MANAGEMENT',
        #'can_retest': False
    #},
    
     'management_approved_2': {
        'display': 'Pending: FM Approval',
        'next_stage': 'MANAGEMENT_2',
        'group': 'MANAGEMENT_2',
        'can_retest': False
    },
    'fm_approved': {
        'display': 'Pending: HOD Approval',
        'next_stage': 'hod_approved',
        'group': 'FM',
        'can_retest': False
    },
    
    
    'hod_approved': {
        'display': 'Pending: Lab Test',
        'next_stage': 'test_completed',
        'group': 'HOD',
        'can_retest': False
    },
    'test_completed': {
        'display': 'Pending: QAO Review',
        'next_stage': 'qao_reviewed',
        'group': 'QC',
        'can_retest': True,
        'retest_chain': ['QAO', 'QC']
    },
    'qao_reviewed': {
        'display': 'Pending: HOD Test Approval',
        'next_stage': 'hod_test_approved',
        'group': 'QAO',
        'can_retest': True,
        'retest_chain': ['HOD_TEST', 'QAO', 'QC']
    },
    'hod_test_approved': {
        'display': 'Pending: Management Test Approval',
        'next_stage': 'management_test_approved',
        'group': 'HOD_TEST',
        'can_retest': True,
        'check_second_approver': True,
        'retest_chain': ['FM_TEST', 'HOD_TEST', 'QAO', 'QC']
    },
    
    'fm_test_approved': {
        'display': 'Pending: Management Test Approval',
        'next_stage': 'management_test_approved',
        'group': 'FM_TEST',
        'can_retest': True,
        'retest_chain': ['FM_TEST','MANAGEMENT_TEST' 'HOD_TEST', 'QAO', 'QC']
    },
    'management_test_approved': {
        'display': 'Pending: Milan Approval',
        'next_stage': 'milan_approved',
        'group': 'MANAGEMENT_TEST',
        'can_retest': True,
        'retest_chain': ['MILAN', 'MANAGEMENT_TEST', 'HOD_TEST', 'QAO', 'QC']
    },
    'milan_approved': {
        'display': 'Completed',
        'next_stage': None,
        'group': 'MILAN',
        'can_retest': False
    },
    'pending_retest': {
        'display': 'Pending: Retest',
        'next_stage': 'retesting',
        'group': 'LAB',
        'can_retest': False
    },
    'retesting': {
        'display': 'Retesting in Progress',
        'next_stage': 'retest_completed',
        'group': 'LAB',
        'can_retest': False
    },
    'retest_completed': {
        'display': 'Retest Completed: Pending Review',
        'next_stage': None,
        'group': None,
        'can_retest': False
    },
    'rejected': {
        'display': 'Rejected',
        'next_stage': None,
        'group': None,
        'can_retest': False
    }
}

# Update the GROUP_STATUS_MAPPING
GROUP_STATUS_MAPPING = {
    'HOD_PURCHASE': ['report_created'],
    'MANAGEMENT': ['hod_purchase_approved', 'management_approved'],
    'MANAGEMENT_2': ['management_approved_2'],
    'FM': ['management_approved_2', 'management_approved'],
    #'HOD': ['management_approved_2', 'management_approved'],
    'HOD': ['fm_approved', 'management_approved'],
    'LAB': ['hod_approved', 'pending_retest', 'retesting'],
    'QAO': ['test_completed', 'pending_retest', 'retesting', 'retest_completed'],
    'HOD_TEST': ['qao_reviewed', 'pending_retest', 'retesting', 'retest_completed'],
    'MANAGEMENT_TEST': ['hod_test_approved', 'pending_retest', 'retesting', 'retest_completed'],
    'MILAN': ['management_test_approved', 'hod_test_approved', 'pending_retest', 'retesting', 'retest_completed'],  # Both flows
    'ADMIN': ['report_created', 'hod_purchase_approved', 'management_approved',
              'management_approved_2', 'hod_approved', 'test_completed', 
              'qao_reviewed', 'hod_test_approved', 'management_test_approved',
              'milan_approved', 'completed', 'rejected', 'pending_retest',
              'retesting', 'retest_completed']
}

# Status display mapping for normalizing status strings
STATUS_DISPLAY_MAPPING = {
    'pending: hod purchase approval': 'report_created',
    'pending hod purchase approval': 'report_created',
    'pending:hod purchase approval': 'report_created',
    'pending : hod purchase approval': 'report_created',
    'Pending: HOD Purchase approval': 'report_created',
    'Pending: HOD Purchase Approval': 'report_created',
    'PENDING: HOD PURCHASE APPROVAL': 'report_created',
    'pending: management approval': 'hod_purchase_approved',
    'pending: management 2nd approval': 'management_approved',
    'pending: fm approval': 'management_approved_2',
    'pending: hod approval': 'fm_approved',
    'pending: lab test': 'hod_approved',
    'pending: qao review': 'test_completed',
    'pending: hod test approval': 'qao_reviewed',
    'pending: fm test approval': 'hod_test_approved',
    'pending: management test approval': 'fm_test_approved',
    'pending: milan approval': 'management_test_approved',
    'completed': 'milan_approved',
    'pending retest': 'pending_retest',
    'retesting': 'retesting',
    'retest completed': 'retest_completed'
}

def normalize_status(status):
    #Normalize status string to internal format
    if not status:
        return ''
    
    status = status.lower().strip()
    
    # Direct status mapping
    status_mapping = {
        'pending: hod purchase approval': 'report_created',
        'pending hod purchase approval': 'report_created',
        'pending: management approval': 'hod_purchase_approved',
        'pending: management 2nd approval': 'management_approved',
        'pending: fm approval': 'management_approved_2',
        'pending: hod approval': 'fm_approved',
        'pending: lab test': 'hod_approved',
        'pending: qao review': 'test_completed',
        'pending: hod test approval': 'qao_reviewed',
        'pending: fm_test_approval' : 'hod_test_approved',
        'pending: management test approval': 'fm_test_approved',
        'pending: milan approval': 'management_test_approved',
        'completed': 'milan_approved',
        'pending retest': 'pending_retest',
        'retesting': 'retesting',
        'retest completed': 'retest_completed'
    }
    if status in status_mapping:
        return status_mapping[status]
    
    # Handle retest variations
    if 'retest' in status:
        if status.startswith('pending retest'):
            return 'pending_retest'
        if 'retesting' in status:
            return 'retesting'
        if 'retest completed' in status:
            return 'retest_completed'
    
    return status

from django.db.models import F, IntegerField
from django.db.models.functions import Cast, Substr

@login_required
def pending(request):
    try:
        user_groups = list(request.user.groups.values_list('name', flat=True))
        logger.info(f"User groups for {request.user.username}: {user_groups}")

        if not user_groups:
            messages.error(request, 'You do not have any assigned roles. Please contact your administrator.')
            return redirect('login')

        # Get accessible statuses for user's groups
        accessible_statuses = []
        for group in user_groups:
            if group in GROUP_STATUS_MAPPING:
                accessible_statuses.extend(GROUP_STATUS_MAPPING[group])

        # Remove duplicates
        accessible_statuses = list(set(accessible_statuses))
        logger.info(f"Accessible statuses: {accessible_statuses}")

        # Handle retest statuses
        retest_groups = ['QAO', 'HOD_TEST', 'FM_TEST', 'MANAGEMENT_TEST', 'LAB', 'ADMIN']
        if any(group in retest_groups for group in user_groups):
            accessible_statuses.extend(['pending_retest', 'retesting', 'retest_completed'])

        # Base queryset with retest status handling
        reports = RMTRRequest.objects.filter(
            Q(status__in=accessible_statuses) |
            Q(status__startswith='pending_retest_') |
            Q(status__startswith='retesting_') |
            Q(status__startswith='retest_completed_')
        ).exclude(status__in=['completed', 'rejected'])

        # Custom ordering by RMTR number
        reports = sorted(
            reports,
            key=lambda x: (
                -int(x.rmtr_no.split('-')[0]),  
                -int(x.rmtr_no.split('-')[1])   
            )
        )

        # Process each report for display
        processed_reports = []
        for report in reports:
            normalized_status = normalize_status(report.status)
            report.internal_status = normalized_status
            
            # Set display status using the mapping
            config = STATUS_CONFIG.get(normalized_status, {})
            report.display_status = config.get('display', report.status)
            
            # Add retest capabilities
            report.can_retest = config.get('can_retest', False)
            if report.can_retest:
                report.retest_chain = config.get('retest_chain', [])
                report.user_can_retest = any(group in report.retest_chain for group in user_groups)
            else:
                report.user_can_retest = False
            
            processed_reports.append(report)

        # Apply search if provided
        search_query = request.GET.get('search')
        if search_query:
            search_query = search_query.lower()
            processed_reports = [
                report for report in processed_reports
                if search_query in report.rmtr_no.lower() or
                   search_query in report.supplier.name.lower() or
                   search_query in report.material_type.lower() or
                   search_query in report.plant.name.lower()
            ]

        # Pagination
        paginator = Paginator(processed_reports, 50)
        page = request.GET.get('page', 1)
        reports = paginator.get_page(page)

        context = {
            'pending_reports': reports,
            'user_groups': user_groups,
            'accessible_statuses': accessible_statuses,
            'search_query': search_query,
            'status_config': STATUS_CONFIG,
            'status_display_mapping': STATUS_DISPLAY_MAPPING
        }

        return render(request, 'pending.html', context)

    except Exception as e:
        logger.exception(f"Error in pending_view: {str(e)}")
        messages.error(request, 'An error occurred while loading the dashboard.')
        return redirect('dashboard')


   


"""
ROUTE_MAPPING = {
    'report_created': {
        'display': 'Pending: HOD Purchase Approval',
        'next': 'hod_purchase_approval',
        'group': 'HOD_PURCHASE, PURCHASE',
        'route': 'hod_purchase_approval'
    },
    'hod_purchase_approved': {
        'display': 'Pending: Management Approval',
        'next': 'management_approval',
        'group': 'HOD_PURCHASE',
        'route': 'management_approval'
    },
    'management_approved': {
        'display': 'Pending: Second Management Approval',
        'next': 'management_approval_2',
        'group': 'MANAGEMENT',
        'route': 'management_approval_2'
    },
    'management_approved_2': {
        'display': 'Pending: FM Approval',
        'next': 'fm_approval',
        'group': 'MANAGEMENT',
        'route': 'fm_approval'
    },
    'fm_approved': {
        'display': 'Pending: HOD Approval',
        'next': 'hod_approval',
        'group': 'FM',
        'route': 'hod_approval'
    },
    'hod_approved': {
        'display': 'Pending: Lab Test',
        'next': 'fill_page',
        'group': 'HOD',
        'route': 'fill_page'
    },
    'test_completed': {
        'display': 'Pending: QAO Review',
        'next': 'qao_test_approval',
        'group': 'LAB',
        'route': 'qao_test_approval'
    },
    'qao_reviewed': {
        'display': 'Pending: HOD Test Approval',
        'next': 'hod_test_approval',
        'group': 'QAO',
        'route': 'hod_test_approval'
    },
    'hod_test_approved': {
        'display': 'Pending: FM Test Approval',
        'next': 'fm_test_approval',
        'group': 'HOD_TEST',
        'route': 'fm_test_approval'
    },
    'fm_test_approved': {
        'display': 'Pending: Management Test Approval',
        'next': 'management_test_approval',
        'group': 'FM_TEST',
        'route': 'management_test_approval'
    },
    'management_test_approved': {
        'display': 'Pending: Milan Approval',
        'next': 'milan_approval',
        'group': 'MANAGEMENT_TEST',
        'route': 'milan_approval'
    },
    'milan_approval': {
        'display': 'Under Final Review',
        'next': 'completed',
        'group': 'MILAN',
        'route': 'milan_approval'
    },
    'completed': {
        'display': 'Completed',
        'next': None,
        'group': 'ADMIN',
        'route': None
    },
    'rejected': {
        'display': 'Rejected',
        'next': None,
        'group': 'ADMIN',
        'route': None
    }
}

# Map groups to their corresponding next statuses
group_status_map = {
    'MILAN': 'management_test_approved',          
    'MANAGEMENT_TEST': 'fm_test_approved',         
    'FM_TEST': 'hod_test_approved',                
    'HOD_TEST': 'qao_reviewed',                    
    'QAO': 'test_completed',                       
    'LAB': 'hod_approved',                         
    'HOD': 'fm_approved',                          
    'FM': 'management_approved',                   
    'MANAGEMENT': 'hod_purchase_approved',         
    'MANAGEMENT_2': 'management_approved_2',       
    'HOD_PURCHASE': 'report_created'               
}
"""
ROUTE_MAPPING = {
    'report_created': {
        'display': 'Pending: HOD Purchase Approval',
        'next': 'hod_purchase_approval',
        'group': 'HOD_PURCHASE, PURCHASE',
        'route': 'hod_purchase_approval'
    },
    'hod_purchase_approved': {
        'display': 'Pending: Management Approval',
        'next': 'management_approval',
        'group': 'HOD_PURCHASE',
        'route': 'management_approval'
    },
    'management_approved': {
        'display': 'Pending: Second Management Approval',
        'next': 'management_approval_2',
        'group': 'MANAGEMENT',
        'route': 'management_approval_2'
    },
    'management_approved_2': {
        'display': 'Pending: HOD Approval',
        'next': 'hod_approval',
        'group': 'MANAGEMENT',
        'route': 'hod_approval'
    },
   
    'hod_approved': {
        'display': 'Pending: Lab Test',
        'next': 'fill_page',
        'group': 'HOD',
        'route': 'fill_page'
    },
    'test_completed': {
        'display': 'Pending: QAO Review',
        'next': 'qao_test_approval',
        'group': 'LAB',
        'route': 'qao_test_approval'
    },
    'qao_reviewed': {
        'display': 'Pending: HOD Test Approval',
        'next': 'hod_test_approval',
        'group': 'QAO',
        'route': 'hod_test_approval'
    },
    'hod_test_approved': {
        'display': 'Pending: Management Test Approval',
        'next': 'management_test_approval',
        'group': 'HOD_TEST',
        'route': 'management_test_approval'
    },
    
    'management_test_approved': {
        'display': 'Pending: Milan Approval',
        'next': 'milan_approval',
        'group': 'MANAGEMENT_TEST',
        'route': 'milan_approval'
    },
    'milan_approval': {
        'display': 'Under Final Review',
        'next': 'completed',
        'group': 'MILAN',
        'route': 'milan_approval'
    },
    'completed': {
        'display': 'Completed',
        'next': None,
        'group': 'ADMIN',
        'route': None
    },
    'rejected': {
        'display': 'Rejected',
        'next': None,
        'group': 'ADMIN',
        'route': None
    }
}

# Map groups to their corresponding next statuses
group_status_map = {
    'MILAN': 'management_test_approved',          
    'MANAGEMENT_TEST': 'hod_test_approved',         
                   
    'HOD_TEST': 'qao_reviewed',                    
    'QAO': 'test_completed',                       
    'LAB': 'hod_approved',                         
    'HOD': 'management_approved',                          
                   
    'MANAGEMENT': 'hod_purchase_approved',         
    'MANAGEMENT_2': 'management_approved_2',       
    'HOD_PURCHASE': 'report_created'               
}

@login_required
def my_rmtr(request):
    """View for displaying only RMTRs that need the current user's attention."""
    try:
        user = request.user
        user_groups = [group.name for group in user.groups.all()]
        
        if not user_groups:
            messages.error(request, 'You do not have any assigned roles. Please contact your administrator.')
            return redirect('login')

        # Initialize query filter
        pending_filter = Q()

        # Get user's plant if they are HOD
        user_plant = None
        if 'HOD' in user_groups:
            user_plant = Plant.objects.filter(hod=user.username).first()

        # Build the filter based on user's groups
        for group in user_groups:
            if group in group_status_map:
                # Get the next status they need to process
                next_status = group_status_map[group]
                pending_filter |= Q(status=next_status)

        # Add plant filter for HOD roles
        if user_plant and ('HOD' in user_groups or 'HOD_TEST' in user_groups):
            pending_filter &= Q(plant=user_plant.name)

        # Get pending RMTRs
        pending_rmtrs = RMTRRequest.objects.filter(pending_filter)

        # Handle search
        search_query = request.GET.get('search')
        if search_query:
            pending_rmtrs = pending_rmtrs.filter(
                Q(rmtr_no__icontains=search_query) |
                Q(supplier__icontains=search_query) |
                Q(material_type__icontains=search_query) |
                Q(plant__icontains=search_query)
            )

        # Handle sorting
        sort_field = request.GET.get('sort', '-date_created')
        pending_rmtrs = pending_rmtrs.order_by(sort_field)

        # Pagination
        paginator = Paginator(pending_rmtrs, 50)
        page = request.GET.get('page', 1)
        rmtrs = paginator.get_page(page)

        context = {
            'rmtrs': rmtrs,
            'user_groups': user_groups,
            'pending_count': pending_rmtrs.count(),
            'search_query': search_query,
            'current_sort': sort_field,
            'route_mapping': ROUTE_MAPPING,  # Pass the updated route mapping
            'user_plant': user_plant.name if user_plant else None
        }

        return render(request, 'my_rmtr.html', context)

    except Exception as e:
        logger.error(f"Error in my_rmtr view: {str(e)}", exc_info=True)
        messages.error(request, 'An error occurred while loading your RMTRs.')
        return redirect('dashboard')

@login_required
def get_target_route(request):
    """API endpoint to get the target route for a given status and user groups."""
    try:
        status = request.GET.get('status', '').lower()
        user_groups = request.GET.get('user_groups', '').split(',')

        # Get the route mapping for the status
        status_config = ROUTE_MAPPING.get(status)
        
        if status_config and status_config['group'] in user_groups:
            return JsonResponse({
                'targetRoute': status_config['route'],
                'status': 'success'
            })
        
        return JsonResponse({
            'targetRoute': None,
            'status': 'error',
            'message': 'No route found for given status and user groups'
        })

    except Exception as e:
        logger.error(f"Error in get_target_route: {str(e)}")
        return JsonResponse({
            'targetRoute': None,
            'status': 'error',
            'message': 'An error occurred'
        }, status=500)

@login_required
def check_pending_rmtrs(request):
    """API endpoint to check for new pending RMTRs."""
    try:
        user_groups = [group.name for group in request.user.groups.all()]
        
        pending_filters = Q()
        for status, group_routes in ROUTE_MAPPING.items():
            for group in user_groups:
                if group in group_routes:
                    pending_filters |= Q(status=status)

        pending_rmtrs = RMTRRequest.objects.filter(pending_filters)\
            .values('rmtr_no', 'status', 'date_created')

        return JsonResponse({
            'pending_rmtrs': list(pending_rmtrs),
            'count': pending_rmtrs.count()
        })

    except Exception as e:
        logger.error(f"Error checking pending RMTRs: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'Failed to check pending RMTRs'
        }, status=500)




def pdf_report(request):
    template = get_template('pdf_report.html')
    context = {'data': 'your_context_data'}  
    html = template.render(context)
    
    try:
        pdf = pdfkit.from_string(html, False)
    except OSError as e:
        logger.error(f'Error generating PDF: {str(e)}')
        return HttpResponse(f'Error generating PDF: {str(e)}')

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="report.pdf"'
    return response

logger = logging.getLogger(__name__)


def upload_rmtr_image(request):
    if request.method == 'POST':
        form = RMTRRequestForm(request.POST, request.FILES)
        if form.is_valid():
            
            rmtr = form.save(commit=False)  

           
            if rmtr.rmtr_no:
                rmtr.image.name = f"rmtr_{rmtr.rmtr_no}/{rmtr.image.name.split('/')[-1]}"
            
            rmtr.save()  

            return JsonResponse({'message': 'Image uploaded successfully!'}, status=201)
        else:
            return JsonResponse({'message': 'Error uploading image', 'errors': form.errors}, status=400)
    else:
        form = RMTRRequestForm()

    return render(request, 'test_request.html', {'form': form})


def create_report(request):
   
    if 'rmtr_no' not in request.session:
      
        new_request = RMTRRequest()
        next_rmtr_no = new_request.generate_next_rmtr_no()  # Generate RMTR number
        request.session['rmtr_no'] = next_rmtr_no 
    # Fetch RMTR No. from the session
    rmtr_no = request.session['rmtr_no']

    # Handle POST request (form submission)
    if request.method == 'POST':
        form = RMTRRequestForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)  
            report.rmtr_no = rmtr_no 
            report.created_by = request.user 

            try:
                # Save the report instance
                report.save()

                # Clear RMTR number from session after save
                del request.session['rmtr_no']

                # Send success response
                return JsonResponse({
                    'status': 'success',
                    'message': 'Report created successfully!',
                    'redirect': '/dashboard/',  # Redirect after success
                })

            except Exception as e:
                # Return an error response
                return JsonResponse({
                    'status': 'error',
                    'message': f'Error creating report: {str(e)}',
                }, status=500)

        else:
            # Handle invalid form errors
            return JsonResponse({
                'status': 'error',
                'message': 'Form is invalid.',
                'errors': form.errors.as_json(),
            }, status=400)

    # Render the form and RMTR No. for GET request
    return render(request, 'test_request.html', {'form': RMTRRequestForm(), 'rmtr_no': rmtr_no})


# Fetch plant and HOD
def plant_hod_data(request):
    plants = Plant.objects.all().values('id', 'name', 'hod')
    plant_hod_mapping = list(plants)
    return JsonResponse(plant_hod_mapping, safe=False)





logger = logging.getLogger(__name__)

# Updated status mapping with more variations
STATUS_DISPLAY_MAPPING = {
    'pending: hod purchase approval': 'report_created',
    'pending hod purchase approval': 'report_created',
    'pending:hod purchase approval': 'report_created',
    'pending : hod purchase approval': 'report_created',
    'Pending: HOD Purchase approval': 'report_created',
    'Pending: HOD Purchase Approval': 'report_created',
    'PENDING: HOD PURCHASE APPROVAL': 'report_created',
    'pending: management approval': 'hod_purchase_approved',
    'pending: management 2nd approval': 'management_approved',
    'pending: fm approval': 'management_approved_2',
    'pending: hod approval': 'fm_approved',
    'pending: lab test': 'hod_approved',
    'pending: qao test approval': 'test_completed',
    'pending: hod test approval': 'qao_test_approval',
    'pending: fm test approval': 'hod_test_approved',
    'pending: management test approval': 'fm_test_approved',
    'pending: milan approval': 'management_test_approved',
    'under final review': 'milan_approval'
}

def normalize_status(status):
    """Convert display status to internal status with detailed logging"""
    if not status:
        logger.warning("Empty status received")
        return ''
        
    original_status = status
    status_lower = status.lower().strip()
    
    # Log the normalization process
    logger.info(f"Normalizing status: Original='{original_status}', Lowercase='{status_lower}'")
    
    normalized = STATUS_DISPLAY_MAPPING.get(status_lower)
    
    if normalized:
        logger.info(f"Status normalized: '{original_status}' -> '{normalized}'")
        return normalized
    
    logger.warning(f"No mapping found for status: '{original_status}'")
    return status_lower

@login_required
def hod_purchase_approval(request, rmtr_no):
    try:
        logger.info(f"Accessing HOD approval for RMTR: {rmtr_no}")
        logger.info(f"User groups: {[g.name for g in request.user.groups.all()]}")

        # Email mapping for approvers - using lowercase for consistent comparison
        APPROVER_EMAILS = {
            'jaivin': 'jaivin@kapa-oil.com',
            'milan': 'milan@kapa-oil.com',
            'neev': 'neev@kapa-oil.com',
            'sid': 'sid@kapa-oil.com'
        }

        # Get the specific report
        report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)
        
        # Log original report state
        logger.info(f"Report found: RMTR {rmtr_no}, Status: {report.status}")
        
        # Normalize the status with detailed logging
        current_status = normalize_status(report.status)
        logger.info(f"Status normalization: Original='{report.status}' -> Normalized='{current_status}'")

        # Permission check
        if not request.user.groups.filter(name__in=['HOD_PURCHASE', 'ADMIN']).exists():
            logger.warning(f"Permission denied for user: {request.user.username}")
            messages.error(request, 'You do not have permission to access this page')
            return redirect('pending')

        # Check if report is in correct state with detailed logging
        if current_status != 'report_created':
            logger.error(f"Invalid report state for RMTR: {rmtr_no}, Status: {report.status}")
            logger.error(f"Normalized status '{current_status}' does not match expected 'report_created'")
            messages.error(request, f'Invalid report state: {report.status}')
            return redirect('pending')

        if request.method == 'POST':
            # Get form data
            approval_status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            priority = request.POST.get('priority')
            sensitivity = request.POST.get('sensitivity')
            current_time = timezone.now()

            logger.info(f"Processing approval for RMTR {rmtr_no}: {approval_status}")

            # Update report
            report.hod_purchase_priority = priority
            report.hod_purchase_sensitivity = sensitivity
            report.hod_purchase_comments = comments

            if approval_status == 'approved':
                report.hod_purchase_approved = True
                report.hod_purchase_rejected = False
                report.hod_purchase_date_approved = current_time
                report.status = 'Pending: Management 1st Approval'
                logger.info(f"RMTR {rmtr_no} approved, new status: hod_purchase_approved")
            else:
                report.hod_purchase_approved = False
                report.hod_purchase_rejected = True
                report.hod_purchase_date_rejected = current_time
                report.status = 'rejected'
                logger.info(f"RMTR {rmtr_no} rejected")

            report.save()
            logger.info(f"RMTR {rmtr_no} updated successfully")

            # Priority mapping for email
            priority_mapping = {
                "1": "Low",
                "2": "Medium",
                "3": "High",
                1: "Low",
                2: "Medium",
                3: "High"
            }

            # Prepare recipients list
            recipients = [
                request.user.email,
                'ict@kapa-oil.com',
                report.created_by.email if report.created_by else None
            ]

            # Add first approver's email if approved
            if approval_status == 'approved':
                # Log the raw approver name for debugging
                logger.info(f"First approver name from report (raw): {report.approved_mgt}")
                
                # Convert approver name to lowercase for comparison
                approver_name = report.approved_mgt.lower() if report.approved_mgt else None
                logger.info(f"First approver name converted to lowercase: {approver_name}")
                
                if approver_name in APPROVER_EMAILS:
                    recipients.append(APPROVER_EMAILS[approver_name])
                    logger.info(f"Added first approver email: {APPROVER_EMAILS[approver_name]}")
                else:
                    logger.error(f"Approver {approver_name} not found in APPROVER_EMAILS dictionary")

            # Filter out None values and remove duplicates
            recipients = list(set(filter(None, recipients)))
            logger.info(f"Final recipient list: {recipients}")

            # Prepare email notification
            subject = f'RMTR Report {rmtr_no} - HOD Purchase {approval_status.title()}'
            message = f"""
            RMTR Report {rmtr_no} has been {approval_status} by HOD Purchase.

            RMTR Details:
            -------------
            RMTR Number: {rmtr_no}
            Status: {approval_status.title()}
            Supplier: {report.supplier}
            Material Type: {report.material_type}
            Material Name: {report.material_name}
            Plant: {report.plant}

            Test to be Done: {report.tests}
            
            Priority: {priority_mapping.get(priority, 'Unknown')}
            Sensitivity: {sensitivity}
           
            Comments: {comments}
            
            Approval Route:
            First Approver: {report.approved_mgt.title()}
            {f'Second Approver: {report.second_approver.title()}' if report.second_approver else ''}
            
            Action By: {request.user.get_full_name() or request.user.username}
            Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}
            Date Created: {report.date_created}

            Raw Material Test Report Link: http://10.0.0.7:8020
            
            Next Stage: {"Management First Approval" if approval_status == "approved" else "Report Rejected"}
            {f"Action Required: First approver ({report.approved_mgt.title()}) to review" if approval_status == "approved" else ""}
            """

            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=True,
                )
                logger.info(f"Email notification sent for RMTR {rmtr_no}")
                logger.info(f"Email sent to recipients: {recipients}")
            except Exception as e:
                logger.error(f"Error sending email for RMTR {rmtr_no}: {str(e)}")

            return JsonResponse({
                'success': True,
                'message': f'Report {approval_status} successfully'
            })

        context = {
            'report': report,
        }
        logger.info(f"Rendering HOD approval template for RMTR {rmtr_no}")
        return render(request, 'hod_purchase_approval.html', context)

    except Exception as e:
        logger.exception(f"Error in HOD purchase approval for RMTR {rmtr_no}")
        messages.error(request, f'An error occurred: {str(e)}')
        return redirect('pending')




@login_required
def edit_rmtr(request, rmtr_no):
 
    try:
        logger.info(f"Accessing RMTR edit for: {rmtr_no}")
        logger.info(f"User groups: {[g.name for g in request.user.groups.all()]}")
        
        # Get the specific report
        report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)
        
        # Permission check
        if not request.user.groups.filter(name__in=['HOD_PURCHASE', 'ADMIN']).exists():
            logger.warning(f"Permission denied for user: {request.user.username}")
            return JsonResponse({
                'success': False,
                'message': 'You do not have permission to edit this RMTR'
            }, status=403)
        
        # Check report state
        current_status = normalize_status(report.status)
        if current_status != 'report_created':
            logger.error(f"Invalid report state for editing RMTR: {rmtr_no}, Status: {report.status}")
            return JsonResponse({
                'success': False,
                'message': f'RMTR cannot be edited in its current state: {report.status}'
            }, status=400)

        if request.method == 'POST':
            try:
                with transaction.atomic():
                    # Update basic information
                    #report.supplier = request.POST.get('supplier')
                    #report.material_type = request.POST.get('material_type')
                    #report.sub_category = request.POST.get('sub_category')
                   #report.tests = request.POST.get('selected_tests')
                    report.uom = request.POST.get('uom')
                    report.quantity = request.POST.get('quantity')
                    report.specs = request.POST.get('specs')
                    #report.plant = get_object_or_404(Plant, name=request.POST.get('plant'))
                    report.justification = request.POST.get('justification')
                    report.approved_mgt = request.POST.get('approved-mgt')

                    # Handle image upload
                    if 'image-upload' in request.FILES:
                        if report.image:
                            report.image.delete(save=False)
                        report.image = request.FILES['image-upload']

                    report.save()
                    logger.info(f"Successfully updated RMTR: {rmtr_no}")
                    
                    # Send notification email
                    try:
                        subject = f'RMTR  {report.rmtr_no} has been Updated'
                        message = f"""
                        RMTR {report.rmtr_no} has been updated by {request.user.get_full_name()}.
                        Date Modified: {timezone.now()}
                        Action BY:  {request.user.get_full_name() or request.user.username}
                        
                        Please review the changes.
                        Raw Material Test Report Link: http://10.0.0.7:8020
                        """
                        
                        recipients = [
                            
                            report.created_by.email,
                            request.user.email,
                            'ict@kapa-oil.com'
                        ]
                        
                        send_mail(
                            subject=subject,
                            message=message,
                            from_email='kapaportal@kapa-oil.local',
                            recipient_list=recipients,
                            fail_silently=True,
                        )
                    except Exception as e:
                        logger.error(f"Error sending notification email: {str(e)}")
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Changes saved successfully'
                    })
                    
            except Exception as e:
                logger.error(f"Error updating RMTR {rmtr_no}: {str(e)}")
                logger.error(traceback.format_exc())
                return JsonResponse({
                    'success': False,
                    'message': f'Error saving changes: {str(e)}'
                }, status=500)

        # GET request - prepare context
        context = {
            'rmtr': report,
            'suppliers': Supplier.objects.all(),
            'plants': Plant.objects.all(),
            'uoms': ['Kgs', 'Ltrs', 'Pcs', 'Tonnes', 'Litres', 'Millilitres', 'Grams']
        }
        
        logger.info(f"Rendering edit form for RMTR {rmtr_no}")
        return render(request, 'edit_rmtr.html', context)
        
    except Exception as e:
        logger.exception(f"Error accessing RMTR edit for {rmtr_no}")
        return JsonResponse({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=500)

@login_required
def get_plant_hod_data(request):
    
    try:
        plants_data = Plant.objects.values('name', 'hod')
        return JsonResponse(list(plants_data), safe=False)
    except Exception as e:
        logger.error(f"Error fetching plant HOD data: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def fetch_material_data(request):
   
    try:
        materials_data = []
        # Query using your MATERIAL_CHOICES
        for material_type in Material.objects.all():
            subcategories_data = []
            # Get subcategories using the related_name
            subcategories = material_type.subcategories.all()
            
            for subcategory in subcategories:
                # Get tests using the related_name
                tests = subcategory.tests.all()
                subcategories_data.append({
                    'name': subcategory.name,
                    'tests': [test.name for test in tests]
                })
            
            materials_data.append({
                'material': material_type.name,  
                'subcategories': subcategories_data
            })

        return JsonResponse({'materials': materials_data})
    except Exception as e:
        logger.error(f"Error fetching material data: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def management_approval(request, rmtr_no):
    try:
        logger.info(f"Accessing management approval for RMTR: {rmtr_no}")
        logger.info(f"User groups: {[g.name for g in request.user.groups.all()]}")

        # Email mapping for approvers
        APPROVER_EMAILS = {
            'jaivin': 'jaivin@kapa-oil.com',
            'milan': 'milan@kapa-oil.com',
            'neev': 'neev@kapa-oil.com',
            'sid': 'sid@kapa-oil.com'
        }

        # Get the specific report
        report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)
        
        # Create priority mapping
        priority_mapping = {
            "1": "Low",
            "2": "Medium",
            "3": "High",
            1: "Low",
            2: "Medium",
            3: "High"
        }

        # Check permissions
        if not request.user.groups.filter(name__in=['MANAGEMENT', 'ADMIN']).exists():
            logger.warning(f"Permission denied for user: {request.user.username}")
            messages.error(request, 'You do not have permission to access this page')
            return redirect('pending')

        if request.method == 'POST':
            try:
                current_time = timezone.now()
                approval_status = request.POST.get('approval_status')
                comments = request.POST.get('comments')
                
                if not approval_status or not comments:
                    logger.error(f"Missing required fields for RMTR {rmtr_no}")
                    return JsonResponse({
                        'success': False,
                        'message': 'Missing required fields'
                    }, status=400)
                
                logger.info(f"Processing management approval for RMTR {rmtr_no}: {approval_status}")
                
                # Update the report fields
                report.management_comments = comments
                
                if approval_status == 'approved':
                    report.management_approved = True
                    report.management_rejected = False
                    report.management_date_approved = current_time
                    
                    # Check if there's a second approver
                    if report.second_approver:
                        report.status = 'Pending: Management 2nd Approval'
                        logger.info(f"RMTR {rmtr_no} approved, moving to second management approval")
                    else:
                        # Skip second approval and go directly to FM approval
                        report.status = 'Pending: FM Approval'
                        report.management_approved_2 = True
                        report.management_date_approved_2 = current_time
                        logger.info(f"RMTR {rmtr_no} approved, skipping second approval and moving to FM approval")

                else:
                    report.management_approved = False
                    report.management_rejected = True
                    report.management_date_rejected = current_time
                    report.status = 'rejected'
                    logger.info(f"RMTR {rmtr_no} rejected by management")

                # Initialize recipients list with ICT
                base_recipients = ['ict@kapa-oil.com', 'purchase.user1@kapa-oil.com', 'purchase.user7@kapa-oil.com']
                if request.user.email:
                    base_recipients.append(request.user.email)

                # Get notification emails based on approval status
                if approval_status == 'approved':
                    if report.second_approver:
                        # Add second approver's email 
                        if report.second_approver.lower() in APPROVER_EMAILS:
                            base_recipients.append(APPROVER_EMAILS[report.second_approver.lower()])
                            logger.info(f"Added second approver email: {APPROVER_EMAILS[report.second_approver.lower()]}")
                    else:
                        # If no second approver, send to the FM (rathod.raj)
                        base_recipients.append('kishore@kapa-oil.com')
                        logger.info("Added FM email as there's no second approver")
                
                # Remove duplicates while preserving order
                recipients = list(dict.fromkeys(filter(None, base_recipients)))
                logger.info(f"Final recipient list: {recipients}")
                
                # Save the report
                report.save()
                logger.info(f"RMTR {rmtr_no} updated successfully")

                # Prepare email notification
                subject = f'RMTR {rmtr_no} - Management {"Approval" if approval_status == "approved" else "Rejection"}'
                message = f"""
                RMTR Details:
                -------------
                RMTR Number: {rmtr_no}

                Status: {approval_status.title()}

                Supplier: {report.supplier}

                Material Type: {report.material_type}

                Material Name: {report.material_name}

                Plant: {report.plant}

                Test to be Done: {report.tests}
                
                Management Comments: {comments}
                
                Approval Route:
                {f'First Approver: {report.approved_mgt.title()}' if report.approved_mgt else ''}
                {f'Second Approver: {report.second_approver.title()}' if report.second_approver else ''}
                
                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                Raw Material Test Report Link: http://10.0.0.7:8020
                
                Next Stage: {
                    "Management Second Approval" if approval_status == "approved" and report.second_approver
                    else "Factory Manager Approval" if approval_status == "approved"
                    else "Report Rejected"
                }
                """

                try:
                    send_mail(
                        subject=subject,
                        message=message,
                        from_email='kapaportal@kapa-oil.local',
                        recipient_list=recipients,
                        fail_silently=True,
                    )
                    logger.info(f"Email notification sent for RMTR {rmtr_no}")
                except Exception as e:
                    logger.error(f"Error sending email for RMTR {rmtr_no}: {str(e)}")
                    # Continue execution even if email fails

                return JsonResponse({
                    'success': True,
                    'message': f'Report {approval_status} successfully',
                    'redirect_url': '/pending/'
                })

            except Exception as inner_e:
                logger.exception(f"Error processing approval for RMTR {rmtr_no}")
                return JsonResponse({
                    'success': False,
                    'message': f'Error processing approval: {str(inner_e)}'
                }, status=500)

        # For GET requests
     
        priority_value = report.hod_purchase_priority
        priority_display = priority_mapping.get(priority_value, 'Unknown')

        context = {
            'report': report,
            'priority_display': priority_display,
            'sensitivity': report.hod_purchase_sensitivity
        }
        logger.info(f"Rendering management approval template for RMTR {rmtr_no}")
        return render(request, 'management_approval.html', context)

    except Exception as e:
        logger.exception(f"Error in Management approval for RMTR {rmtr_no}")
        messages.error(request, f'An error occurred: {str(e)}')
        return redirect('pending')



User = get_user_model()
@login_required
def management_approval_2(request, rmtr_no):
    try:
        logger.info(f"Accessing Management 2nd approval for RMTR: {rmtr_no}")
        logger.info(f"User groups: {[g.name for g in request.user.groups.all()]}")

        report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)
        
        logger.info(f"Report found: RMTR {rmtr_no}, Status: {report.status}")
        
        current_status = normalize_status(report.status)
        logger.info(f"Status normalization: Original='{report.status}' -> Normalized='{current_status}'")

        # Permission check
        if not request.user.groups.filter(name__in=['MANAGEMENT', 'ADMIN']).exists():
            logger.warning(f"Permission denied for user: {request.user.username}")
            return JsonResponse({
                'success': False,
                'message': 'You do not have permission to access this page'
            }, status=403)

        # Status check
        if current_status != 'management_approved':
            logger.error(f"Invalid report state for RMTR: {rmtr_no}, Status: {report.status}")
            return JsonResponse({
                'success': False,
                'message': f'Invalid report state: {report.status}'
            }, status=400)

        if request.method == 'POST':
            approval_status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            current_time = timezone.now()

            logger.info(f"Processing 2nd management approval for RMTR {rmtr_no}: {approval_status}")

            with transaction.atomic():
                if approval_status == 'approved':
                    report.management_approved_2 = True
                    report.management_rejected_2 = False
                    report.management_date_approved_2 = current_time
                    report.status = 'Pending: FM Approval'
                    logger.info(f"RMTR {rmtr_no} approved, new status: management_approved_2")
                else:
                    report.management_approved_2 = False
                    report.management_rejected_2 = True
                    report.management_date_rejected_2 = current_time
                    report.status = 'rejected'
                    logger.info(f"RMTR {rmtr_no} rejected")

                report.management_comments_2 = comments
                report.save()

            # Set up recipients list
            base_recipients = [
                'ict@kapa-oil.com',
                'kishore@kapa-oil.com',
                request.user.email
            ]
            
            # If approved, add FM (Rathod) - NOT plant HODs
            if approval_status == 'approved':
                # Add FM and purchase contacts when management second approval is given
                base_recipients.extend([
                    'kishore@kapa-oil.com',
                    'ict@kapa-oil.com',
                    'purchase.user1@kapa-oil.com',
                    'purchase.user7@kapa-oil.com',
                ])
                logger.info("Added FM and purchase emails to recipient list")

            # Remove duplicates and None values
            recipients = list(filter(None, dict.fromkeys(base_recipients)))
            logger.info(f"Final recipient list: {recipients}")

            # Send email notification
            try:
                subject = f'RMTR {rmtr_no} - Management (Second) {"Approval" if approval_status == "approved" else "Rejection"}'
                message = f"""
                RMTR Details:
                -------------
                RMTR Number: {rmtr_no}
                Status: {approval_status.title()}

                Material Type: {report.material_type}

                Material Name: {report.material_name}

                Supplier: {report.supplier}

                Plant: {report.plant}

                Tests to be Done: {report.tests}

                
                Management (Second) Comments: {comments}
                
                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}
                
                Raw Material Test Report Link: http://10.0.0.7:8020
                
                Next Stage: {"Factory Manager Approval Required" if approval_status == "approved" else "Request Rejected"}
                """
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=True
                )
                logger.info(f"Email sent successfully for RMTR {rmtr_no} to {recipients}")
            except Exception as e:
                logger.error(f"Failed to send email for RMTR {rmtr_no}: {str(e)}")
                # Continue execution even if email fails

            return JsonResponse({
                'success': True,
                'message': f'Report {approval_status} successfully',
                'redirect_url': '/pending/'  
            })

        # For GET requests
        context = {
            'report': report,
        }
        logger.info(f"Rendering management approval 2 template for RMTR {rmtr_no}")
        return render(request, 'management_approval_2.html', context)

    except RMTRRequest.DoesNotExist:
        logger.error(f"RMTR {rmtr_no} not found")
        return JsonResponse({
            'success': False,
            'message': f'RMTR {rmtr_no} not found'
        }, status=404)
    except Exception as e:
        logger.exception(f"Error in management approval 2 for RMTR {rmtr_no}")
        return JsonResponse({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=500)


@login_required
def fm_approval(request, rmtr_no):
    try:
        logger.info(f"Accessing FM approval for RMTR: {rmtr_no}")
        logger.info(f"User groups: {[g.name for g in request.user.groups.all()]}")
        
        # Get the specific report
        report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)
        
        # Check permissions
        if not request.user.groups.filter(name__in=['FM', 'ADMIN']).exists():
            logger.warning(f"Permission denied for user: {request.user.username}")
            messages.error(request, 'You do not have permission to access this page')
            return redirect('pending')

        if request.method == 'POST':
            try:
                current_time = timezone.now()
                approval_status = request.POST.get('approval_status')
                comments = request.POST.get('comments')
                
                if not approval_status or not comments:
                    logger.error(f"Missing required fields for RMTR {rmtr_no}")
                    return JsonResponse({
                        'success': False,
                        'message': 'Missing required fields'
                    }, status=400)
                
                logger.info(f"Processing FM approval for RMTR {rmtr_no}: {approval_status}")
                
                # Update the report fields
                report.fm_comments = comments
                
                if approval_status == 'approved':
                    report.fm_approved = True
                    report.fm_rejected = False
                    report.fm_date_approved = current_time
                    report.status = 'Pending: HOD Approval'
                    logger.info(f"RMTR {rmtr_no} approved by FM, moving to HOD approval")
                else:
                    report.fm_approved = False
                    report.fm_rejected = True
                    report.fm_date_rejected = current_time
                    report.status = 'rejected'
                    logger.info(f"RMTR {rmtr_no} rejected by FM")
                
                # Initialize recipients list with ICT and current user
                base_recipients = ['ict@kapa-oil.com']
                if request.user.email:
                    base_recipients.append(request.user.email)
                
                # If approved, add plant HOD emails
                if approval_status == 'approved':
                    try:
                        plant = Plant.objects.get(name=report.plant)
                        plant_emails = plant.get_notification_emails()
                        if isinstance(plant_emails, (list, tuple)):
                            base_recipients.extend(plant_emails)
                        elif isinstance(plant_emails, str):
                            base_recipients.append(plant_emails)
                        logger.info(f"Added plant notification emails for {report.plant}")
                    except Plant.DoesNotExist:
                        logger.warning(f"Plant not found for {report.plant}, using default emails")
                
                # Remove duplicates while preserving order
                recipients = list(dict.fromkeys(filter(None, base_recipients)))
                logger.info(f"Final recipient list: {recipients}")
                
                # Save the report
                report.save()
                logger.info(f"RMTR {rmtr_no} updated successfully")

                # Prepare email notification
                subject = f'RMTR {rmtr_no} - Factory Manager {"Approval" if approval_status == "approved" else "Rejection"}'
                message = f"""
                RMTR Details:
                -------------
                RMTR Number: {rmtr_no}

                Status: {approval_status.title()}

                Supplier: {report.supplier}

                Material Type: {report.material_type}

                Material Name: {report.material_name}

                Plant: {report.plant}

                Test to be Done: {report.tests}
                
                Factory Manager Comments: {comments}
                
                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                Raw Material Test Report Link: http://10.0.0.7:8020
                
                Next Stage: {
                    f"HOD {report.plant} Approval" if approval_status == "approved"
                    else "Report Rejected"
                }
                """

                try:
                    send_mail(
                        subject=subject,
                        message=message,
                        from_email='kapaportal@kapa-oil.local',
                        recipient_list=recipients,
                        fail_silently=True,
                    )
                    logger.info(f"Email notification sent for RMTR {rmtr_no}")
                except Exception as e:
                    logger.error(f"Error sending email for RMTR {rmtr_no}: {str(e)}")
                    # Continue execution even if email fails

                return JsonResponse({
                    'success': True,
                    'message': f'Report {approval_status} successfully',
                    'redirect_url': '/pending/'
                })

            except Exception as inner_e:
                logger.exception(f"Error processing approval for RMTR {rmtr_no}")
                return JsonResponse({
                    'success': False,
                    'message': f'Error processing approval: {str(inner_e)}'
                }, status=500)

        # For GET requests, prepare the context
        context = {
            'report': report
        }
        logger.info(f"Rendering FM approval template for RMTR {rmtr_no}")
        return render(request, 'fm_approval.html', context)

    except Exception as e:
        logger.exception(f"Error in FM approval for RMTR {rmtr_no}")
        messages.error(request, f'An error occurred: {str(e)}')
        return redirect('pending')
    


"""
@login_required
def hod_approval(request, rmtr_no):
    try:
        report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)
        
        # Check permissions
        if not request.user.groups.filter(name__in=['HOD','HOD_TEST', 'ADMIN']).exists():
            messages.error(request, 'You do not have permission to access this page')
            return redirect('pending')


        if request.method == 'POST':
            status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            current_time = timezone.now()

            # Update report status
            if status == 'approved':
                report.hod_approved = True
                report.hod_rejected = False
                report.status = 'Pending: Lab Test'
                report.hod_date_approved = current_time
            elif status == 'rejected':
                report.hod_approved = False
                report.hod_rejected = True
                report.status = 'rejected'
                report.hod_date_rejected = current_time

            report.hod_comments = comments
            report.save()

            # Send email notification
            try:
                recipients = [
                    'ict@kapa-oil.com',
                    'qao.user18@kapa-oil.com',
                    'qao.user9@kapa-oil.com',
                    'qao.user4@kapa-oil.com',
                    'qao.user7@kapa-oil.com',
                    'qao.user3@kapa-oil.com',
                    'qao.user1@kapa-oil.com',
                    'qao.user2@kapa-oil.com',
                    'qao.user8@kapa-oil.com',
                    request.user.email
                    
                ]

                subject = f'RMTR {rmtr_no} - HOD {report.plant.name} {"Approval" if status == "approved" else "Rejection"}'
                message = f'''
                RMTR Details:
                -------------
                RMTR Number: {rmtr_no}
                Status: {status.title()}
                Material Type: {report.material_type}
                Material Name: {report.material_name}
                Supplier: {report.supplier}
                
                HOD Comments: {comments}
                
                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                Raw Material Test Report Link: http://10.0.0.7:8020
                
                '''
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list= recipients,
                    fail_silently=True
                  )
            except Exception as e:
                logger.error(f"Failed to send email for RMTR {rmtr_no}: {str(e)}")

            return JsonResponse({
                'success': True,
                'message': f'Request {status} successfully'
            })

        context = {
            'report': report,
            'page_title': 'HOD Approval'
        }
        return render(request, 'hod_approval.html', context)

    except Exception as e:
        logger.error(f"Error in HOD approval: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'An error occurred while processing your request'
        }, status=500)
        
 """
 
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.core.mail import send_mail
from django.contrib import messages
from django.db import transaction
from datetime import datetime, time, timedelta
from typing import List, Dict, Optional
from .models import RMTRRequest
import logging

logger = logging.getLogger(__name__)

class DeadlineConfig:
    """Deadline configurations for different stages"""
    
    # Timeline configurations (in hours)
    RMTR_TIMELINES = {
        'Pending: HOD Purchase Approval': {'hours': 12},
        'Pending: Management 1st Approval': {'hours': 12},
        'Pending: Management 2nd Approval': {'hours': 12},
        
        'Pending: HOD Approval': {'hours': 12},
        'Pending: Lab Test': {'hours': None},  
        'Pending: QAO Review': {'hours': 12},
        'Pending: HOD Test Approval': {'hours': 12},
        'Pending: Management Test Approval': {'hours': 12}
    }

class EmailConfig:
    """Email configurations for different stages"""
    
    # Base mandatory recipients
    MANDATORY_RECIPIENTS = ['ict@kapa-oil.com', 'purchase.user1@kapa-oil.com']
    
    # Stage-specific recipient configurations for RMTR
    RMTR_STAGE_RECIPIENTS = {
        'Pending: HOD Purchase Approval': {
            'fixed_recipients': [
                'purchase.user2@kapa-oil.com',
                'purchase.user10@kapa-oil.com',
                'purchase.user7@kapa-oil.com',
                'purchase.user9@kapa-oil.com',
                'purchase.user5@kapa-oil.com',
                'purchase.user4@kapa-oil.com',
                
            ],
            'include_creator': True
        },
        'Pending: Management 1st Approval': {
            'dynamic_approvers': True
        },
        'Pending: Management 2nd Approval': {
            'dynamic_approvers': True
        },
        'Pending: HOD Approval': {
            'include_plant_hod': True
        },
        'Pending: Lab Test': {
            'fixed_recipients': [
                'qao.user18@kapa-oil.com',
                'qao.user9@kapa-oil.com',
                'qao.user4@kapa-oil.com',
                'qao.user7@kapa-oil.com',
                'qao.user50@kapa-oil.com',
                'qao.user28@kapa-oil.com',
                'qao.user3@kapa-oil.com',
                'qao.user1@kapa-oil.com',
                'qao.user2@kapa-oil.com',
                'qao.user8@kapa-oil.com',
                'qao.user47@kapa-oil.com'
            ]
        },
        'Pending: QAO Review': {
            'fixed_recipients': [
                'qao.user6@kapa-oil.com',
                'qao.user47@kapa-oil.com',
                'qao.user2@kapa-oil.com',
                'qao.user8@kapa-oil.com',
                'qao.user47@kapa-oil.com'
                
            ]
        },
        'Pending: HOD Test Approval': {
            'include_plant_hod': True
        },
        'Pending: Management Test Approval': {
            'dynamic_approvers': True
        }
    }

    @classmethod
    def get_recipients(cls, status: str, report, is_import: bool = False) -> List[str]:
        """Get email recipients for a specific status"""
        recipients = cls.MANDATORY_RECIPIENTS.copy()
        
        # Get stage config based on report type
        stage_config = cls.RMTR_STAGE_RECIPIENTS.get(status, {})
        
        # Add fixed recipients for the stage
        recipients.extend(stage_config.get('fixed_recipients', []))

        # Add creator's email if needed
        if stage_config.get('include_creator', False) and hasattr(report, 'created_by'):
            if report.created_by and report.created_by.email:
                recipients.append(report.created_by.email)

        # Add plant HOD emails if needed
        if stage_config.get('include_plant_hod', False) and hasattr(report, 'plant'):
            try:
                if report.plant.hod_email:
                    recipients.append(report.plant.hod_email)
                if report.plant.deputy_hod_email:
                    recipients.append(report.plant.deputy_hod_email)
                if hasattr(report.plant, 'get_notification_emails'):
                    plant_emails = report.plant.get_notification_emails()
                    if isinstance(plant_emails, (list, tuple)):
                        recipients.extend(plant_emails)
                    elif isinstance(plant_emails, str):
                        recipients.append(plant_emails)
            except Exception as e:
                logger.error(f"Error getting plant HOD emails: {str(e)}")

        # Add current user if available
        if hasattr(report, 'current_user') and report.current_user and report.current_user.email:
            recipients.append(report.current_user.email)

        # Remove duplicates while preserving order
        return list(dict.fromkeys(filter(None, recipients)))

def add_business_days(date, days):
    """Add business days to a date excluding weekends"""
    current_date = date
    remaining_days = days
    
    while remaining_days > 0:
        current_date += timedelta(days=1)
        if current_date.weekday() < 5:  # 0-4 are weekdays
            remaining_days -= 1
    
    return current_date

def calculate_lab_deadline(current_time, days):
    """Calculate lab deadline based on business days"""
    # Start from next business day
    start_date = current_time.date()
    if current_time.hour >= 17:  # If after 5 PM, start from next day
        start_date += timedelta(days=1)
    while start_date.weekday() >= 5:  # Skip weekends
        start_date += timedelta(days=1)
        
    end_date = add_business_days(start_date, days)
    return datetime.combine(end_date, time(17, 0))  # 5 PM on deadline day

def get_business_hours_elapsed(start_date, end_date):
    """Calculate business hours elapsed between two dates"""
    if start_date > end_date:
        return 0
    
    total_hours = 0
    current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date_normalized = end_date.replace(hour=23, minute=59, second=59)
    
    while current_date <= end_date_normalized:
        if current_date.weekday() < 5:  # Weekday
            if current_date.date() == start_date.date():
                work_start = max(start_date.hour, 8)
                work_end = min(17, end_date.hour if current_date.date() == end_date.date() else 17)
                day_hours = max(0, work_end - work_start)
            elif current_date.date() == end_date.date():
                day_hours = min(end_date.hour, 17) - 8
            else:
                day_hours = 9  # Full workday (8 AM to 5 PM)
            total_hours += max(0, day_hours)
        current_date += timedelta(days=1)
    
    return total_hours



@login_required
def hod_approval(request, rmtr_no):
    try:
        logger.info(f"Accessing HOD approval for RMTR: {rmtr_no}")
        logger.info(f"User groups: {[g.name for g in request.user.groups.all()]}")

        report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)

        # Check permissions
        if not request.user.groups.filter(name__in=['HOD', 'HOD_TEST', 'ADMIN']).exists():
            logger.warning(f"Permission denied for user {request.user.username}")
            messages.error(request, 'You do not have permission to access this page')
            return redirect('pending')

        if request.method == 'POST':
            try:
                status = request.POST.get('approval_status')
                comments = request.POST.get('comments')
                lab_timeline_days = request.POST.get('labtimelines')
                current_time = timezone.now()

                # Calculate time taken for approval
                if hasattr(report, 'last_status_change') and report.last_status_change:
                    hours_taken = get_business_hours_elapsed(report.last_status_change, current_time)
                    timeline_config = DeadlineConfig.RMTR_TIMELINES.get(report.status, {'hours': 12})
                    was_delayed = hours_taken > timeline_config['hours']
                    
                    timeline_info = f"""
                    Timeline Information:
                    -------------------
                    Time Taken: {round(hours_taken, 1)} business hours
                    Expected Timeline: {timeline_config['hours']} business hours
                    Status: {'Process DELAYED' if was_delayed else 'Within Timeline'}
                    """
                else:
                    timeline_info = "Timeline tracking has been started"

                # Validate lab timeline for approval
                if status == 'approved' and not lab_timeline_days:
                    return JsonResponse({
                        'success': False,
                        'message': 'Please select lab timeline before approving'
                    }, status=400)

                with transaction.atomic():
                    # Update report status
                    if status == 'approved':
                        report.hod_approved = True
                        report.hod_rejected = False
                        report.status = 'Pending: Lab Test'
                        report.hod_date_approved = current_time
                        report.last_status_change = current_time

                        # Set lab timeline and deadline
                        try:
                            days = int(lab_timeline_days)
                            if 1 <= days <= 10:
                                report.lab_timeline_days = days
                                report.lab_deadline = calculate_lab_deadline(current_time, days)
                                logger.info(f"Lab timeline set: {days} days, deadline: {report.lab_deadline}")
                            else:
                                report.lab_timeline_days = 3
                                report.lab_deadline = calculate_lab_deadline(current_time, 3)
                                logger.warning(f"Invalid lab timeline ({days}), using default (3 days)")
                        except (ValueError, TypeError) as e:
                            logger.error(f"Error setting lab timeline: {str(e)}")
                            report.lab_timeline_days = 3
                            report.lab_deadline = calculate_lab_deadline(current_time, 3)

                    else:  # rejected
                        report.hod_approved = False
                        report.hod_rejected = True
                        report.status = 'rejected'
                        report.hod_date_rejected = current_time
                        report.last_status_change = current_time

                    report.hod_comments = comments
                    report.hod_by = request.user
                    report.save()

                    # Add timeline info for email
                    if status == 'approved' and hasattr(report, 'lab_deadline'):
                        timeline_info += f"""
                        Lab Timeline:
                        ------------
                        Days Allocated: {report.lab_timeline_days} business days
                        Deadline: {report.lab_deadline.strftime('%Y-%m-%d %H:%M')}
                        """

                    # Get recipients using EmailConfig
                    report.current_user = request.user  # Set current user for email config
                    recipients = EmailConfig.get_recipients(report.status, report, is_import=False)

                    subject = f'RMTR {rmtr_no} - HOD {report.plant.name} {"Approval" if status == "approved" else "Rejection"}'
                    message = f"""
                    RMTR Details:
                    -------------
                    RMTR Number: {rmtr_no}
                    Status: {status.title()}
                    Material Name: {report.material_name}
                    Material Type: {report.material_type}
                    Supplier: {report.supplier}
                    Plant: {report.plant}
                    
                    HOD Comments: {comments}
                    
                    {timeline_info}
                    
                    Action By: {request.user.get_full_name() or request.user.username}
                    Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                    Raw Material Test Report Link: http://10.0.0.7:8020
                    """

                    try:
                        send_mail(
                            subject=subject,
                            message=message,
                            from_email='kapaportal@kapa-oil.local',
                            recipient_list=recipients,
                            fail_silently=True
                        )
                        logger.info(f"Email notification sent successfully for RMTR {rmtr_no}")
                    except Exception as e:
                        logger.error(f"Failed to send email for RMTR {rmtr_no}: {str(e)}")

                    return JsonResponse({
                        'success': True,
                        'message': f'Request {status} successfully',
                        'redirect_url': '/pending/'
                    })

            except Exception as process_error:
                logger.error(f"Error processing approval for RMTR {rmtr_no}: {str(process_error)}")
                return JsonResponse({
                    'success': False,
                    'message': 'An error occurred while processing the approval'
                }, status=500)

        # Prepare context for GET request
        context = {
            'report': report,
            'page_title': 'HOD Approval',
            'lab_timeline_options': [
                {'days': i, 'display': f'{i} {"day" if i == 1 else "days"}'}
                for i in range(1, 11)
            ],
            'default_lab_timeline': 3
        }
        logger.info(f"Rendering HOD approval template for RMTR {rmtr_no}")
        return render(request, 'hod_approval.html', context)

    except Exception as e:
        logger.exception(f"Error in HOD approval for RMTR {rmtr_no}")
        messages.error(request, f'An error occurred: {str(e)}')
        return redirect('pending')


        
        
        
# Test Results Submission View
def submit_test_results(request, rmtr_no):
    report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)

    if request.method == 'POST':
        form = TestResultsForm(request.POST)
        if form.is_valid():
            test_result = form.save(commit=False)
            test_result.report = report
            test_result.save()

            # Update RMTRRequest status
            report.status = 'Test Done'
            report.save()

            # Send email notification
            send_mail(
                subject='Test Results Submitted',
                message=f'The test results for RMTR request {rmtr_no} have been submitted.',
                from_email='ict@kapa-oil.com',
                recipient_list=[report.created_by.email],
                fail_silently=False,
            )

            messages.success(request, 'Test results submitted successfully.')
            return redirect('next_stage_view')  # Redirect to the next approval stage

    else:
        form = TestResultsForm()

    return render(request, 'fill_page.html', {'form': form, 'report': report})

@login_required
def retest_request(request, rmtr_no):
   try:
       logger.info(f"Accessing retest request for RMTR: {rmtr_no}")

       # Get the report
       report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)

       # Check permissions
       if not request.user.groups.filter(name__in=['QAO', 'HOD_TEST', 'FM_TEST', 'MANAGEMENT_TEST', 'ADMIN']).exists():
           messages.error(request, 'You do not have permission to request a retest.')
           logger.warning(f"Permission denied for user: {request.user.username}")
           return redirect('pending')

       if request.method == 'POST':
           try:
               # Get form data
               retest_reason = request.POST.get('retest_reason')
               comments = request.POST.get('comments')
               current_time = timezone.now()

               # Validate retest_reason
               if not retest_reason or not retest_reason.strip():
                   logger.error("Invalid retest reason provided")
                   return JsonResponse({
                       'success': False,
                       'message': 'Please provide a valid reason for retest.'
                   }, status=400)

               logger.info(f"Processing retest request for RMTR: {rmtr_no}")

               with transaction.atomic():
                   # Store previous state
                   previous_status = report.status

                   # Update report
                   report.retest_requested = True
                   report.retest_reason = retest_reason.strip()
                   report.status = 'pending_retest'
                   report.qao_comments = comments.strip() if comments else ''
                   
                   # Reset approval flags to allow re-approval after retest
                   report.qao_approved = False
                   report.hod_test_approved = False
                   report.fm_test_approved = False
                   report.management_test_approved = False
                   report.qao_approval_date = None
                   report.hod_test_approval_date = None
                   report.fm_test_approval_date = None
                   report.management_test_approval_date = None
                   
                   report.save()
                   logger.info(f"Report {rmtr_no} updated successfully")

                   # Base recipient list with mainstay recipients
                   recipients = [
                       'ict@kapa-oil.com',
                       'qao.user18@kapa-oil.com',
                       'qao.user9@kapa-oil.com',
                       'qao.user4@kapa-oil.com',
                       'qao.user7@kapa-oil.com',
                       'qao.user50@kapa-oil.com',
                       'qao.user28@kapa-oil.com',
                       'qao.user3@kapa-oil.com',
                       'qao.user1@kapa-oil.com',
                       'qao.user6@kapa-oil.com',
                       'qao.user47@kapa-oil.com',
                   ]

                   # Add user's email if available
                   if request.user.email:
                       recipients.append(request.user.email)

                   # Add role-specific recipients
                   if request.user.groups.filter(name='QAO').exists():
                       recipients.extend([
                           'qao.user6@kapa-oil.com',
                           'qao.user47@kapa-oil.com'
                       ])
                   elif request.user.groups.filter(name='HOD_TEST').exists():
                       recipients.extend([
                           
                           'qao.user6@kapa-oil.com',
                           'qao.user47@kapa-oil.com'
                       ])
                   elif request.user.groups.filter(name='FM_TEST').exists():
                       recipients.extend([
                           'qao.user6@kapa-oil.com',
                           'qao.user47@kapa-oil.com'
                       ])
                   elif request.user.groups.filter(name='MANAGEMENT_TEST').exists():
                       recipients.extend([
                           'qao.user6@kapa-oil.com',
                           'qao.user47@kapa-oil.com'
                       ])

                   # Remove duplicates while preserving order
                   recipients = list(dict.fromkeys(recipients))

                   # Prepare email content
                   subject = f'RMTR {rmtr_no} - Retest Requested'
                   message = f"""
                   RMTR Details:
                   -------------
                   RMTR Number: {rmtr_no}
                   Status: Pending Retest
                   Material: {report.material_type}
                   Supplier: {report.supplier}
                   
                   Retest Reason: {retest_reason}
                   Comments: {comments}
                   
                   Requested By: {request.user.get_full_name() or request.user.username}
                   Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                    Raw Material Test Report Link: http://10.0.0.7:8020
                   """

                   try:
                       send_mail(
                           subject=subject,
                           message=message,
                           from_email='kapaportal@kapa-oil.local',
                           recipient_list=recipients,
                           fail_silently=True
                       )
                       logger.info(f"Retest notification email sent successfully for RMTR {rmtr_no}")
                   except Exception as email_error:
                       logger.error(f"Failed to send retest notification email for RMTR {rmtr_no}: {str(email_error)}")
                       # Continue execution even if email fails

               return JsonResponse({
                   'success': True,
                   'message': 'Retest request submitted successfully.',
                   'redirect_url': '/pending/'
               })

           except Exception as inner_e:
               logger.error(f"Error processing retest request: {str(inner_e)}")
               return JsonResponse({
                   'success': False,
                   'message': 'Error processing retest request'
               }, status=500)

       # GET request - render template
       context = {
           'report': report,
           'page_title': 'Request Retest'
       }

       return render(request, 'retest_request.html', context)

   except Exception as e:
       logger.exception(f"Error in retest_request: {str(e)}")
       messages.error(request, f'An error occurred: {str(e)}')
       return redirect('pending')



    
def handle_retest_request(request, report, data):
   """Handle initial retest request"""
   retest_reason = data.get('retest_reason', '').strip()
   comments = data.get('comments', '').strip()

   if not retest_reason:
       return JsonResponse({
           'success': False,
           'message': 'Please provide a reason for retest.'
       }, status=400)

   # Create retest request
   retest = RetestRequest.objects.create(
       rmtr=report,
       requested_by=request.user,
       reason=retest_reason,
       comments=comments,
       original_status=report.status
   )

   # Update report status
   report.retest_requested = True
   report.status = 'pending_retest'
   report.save()

   # Send notification email
   send_retest_notification(request, report, retest)

   return JsonResponse({
       'success': True,
       'message': 'Retest request submitted successfully.',
       'redirect_url': '/pending/'
   })



def handle_retest_results(request, report, data):
    """Handle retest results submission"""
    test_data = {}
    
    # Collect test data
    for i in range(1, 17):
        test_name = data.get(f'tests_carried_out{i}')
        if test_name:
            test_data[str(i)] = {
                'test': test_name,
                'sample': data.get(f'sample_results{i}'),
                'raw_material': data.get(f'raw_material_results{i}'),
                'standards': data.get(f'kapa_standards{i}')
            }

    if not test_data:
        return JsonResponse({
            'success': False,
            'message': 'At least one test result is required'
        }, status=400)

    # Get latest retest request
    retest = RetestRequest.objects.filter(rmtr=report, completed=False).latest('requested_at')
    
    # Update retest data
    retest.test_data = test_data
    retest.completed = True
    retest.save()

    # Update report
    report.status = 'retest_completed'
    report.save()

    # Send completion notification
    send_retest_completion_notification(request, report, retest)

    return JsonResponse({
        'success': True,
        'message': 'Retest results submitted successfully.',
        'redirect_url': '/pending/'
    })

def send_retest_notification(request, report, retest):
   """Send retest request notification"""
   subject = f'RMTR {report.rmtr_no} - Retest Requested'
   message = f"""
   RMTR Details:
   -------------
   RMTR Number: {report.rmtr_no}
   Status: Pending Retest
   Material: {report.material_type}
   Supplier: {report.supplier}
   
   Retest Reason: {retest.reason}
   Additional Comments: {retest.comments}

   
   Requested By: {request.user.get_full_name() or request.user.username}
   Date: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}

    Raw Material Test Report Link: http://10.0.0.7:8020
   """

   # Build recipient list based on user's group
   recipients = [
       'ict@kapa-oil.com',
       'qao.user18@kapa-oil.com',
       'qao.user9@kapa-oil.com',
       'qao.user4@kapa-oil.com',
       'qao.user7@kapa-oil.com',
       'qao.user3@kapa-oil.com',
       'qao.user47@kapa-oil.com',
       'qao.user50@kapa-oil.com',
       'qao.user28@kapa-oil.com',
       'purchase.user1@kapa-oil.com',
   ]

   # Add user's email if available
   if request.user.email:
       recipients.append(request.user.email)

   user_groups = request.user.groups.all()
   
   if any(g.name == 'QAO' for g in user_groups):
       recipients.extend(['qao.user6@kapa-oil.com', 'qao.user'])
   elif any(g.name == 'HOD_TEST' for g in user_groups):
       recipients.extend(['hod_test@kapa-oil.com', 'qao@kapa-oil.com'])
   elif any(g.name == 'FM_TEST' for g in user_groups):
       recipients.extend(['fm_test@kapa-oil.com', 'hod_test@kapa-oil.com', 'qao@kapa-oil.com'])
   elif any(g.name == 'MANAGEMENT_TEST' for g in user_groups):
       recipients.extend([
           'ict@kapa-oil.com',
           'fm_test@kapa-oil.com',
           'hod_test@kapa-oil.com',
           'qao@kapa-oil.com'
       ])

   # Remove duplicates while preserving order
   recipients = list(dict.fromkeys(recipients))

   try:
       send_mail(
           subject=subject,
           message=message,
           from_email='kapaportal@kapa-oil.local',
           recipient_list=recipients,
           fail_silently=True
       )
       logger.info(f"Retest notification email sent successfully for RMTR {report.rmtr_no}")
   except Exception as e:
       logger.error(f"Failed to send retest notification email: {str(e)}")


def send_retest_completion_notification(request, report, retest):
   """Send retest completion notification"""
   # Format test results for email
   test_results = "\nTest Results:\n-------------\n"
   for test_num, data in retest.test_data.items():
       test_results += f"""
       Test: {data['test']}
       Sample Results: {data['sample']}
       Raw Material Results: {data['raw_material']}
       Standards: {data['standards']}
       -------------
       """

   subject = f'RMTR {report.rmtr_no} - Retest Completed'
   message = f"""
   RMTR Details:
   -------------
   RMTR Number: {report.rmtr_no}
   Material: {report.material_type}
   Supplier: {report.supplier}
   
   {test_results}
   
   Originally Requested By: {retest.requested_by.get_full_name() or retest.requested_by.username}
   Completed By: {request.user.get_full_name() or request.user.username}
   Date: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}

    Raw Material Test Report Link: http://10.0.0.7:8020
   """

   recipients = [
       'ict@kapa-oil.com',
       'qao.user18@kapa-oil.com',
       'qao.user9@kapa-oil.com',
       'qao.user4@kapa-oil.com',
       'qao.user7@kapa-oil.com',
       'qao.user3@kapa-oil.com',
       'qao.user50@kapa-oil.com',
       'qao.user28@kapa-oil.com',
       'qao.user47@kapa-oil.com',
       'qao.user6@kapa-oil.com'
   ]

   # Add original requestor's email if available
   if retest.requested_by and retest.requested_by.email:
       recipients.append(retest.requested_by.email)
       
   # Add role-specific recipients based on original requestor's groups
   requestor_groups = retest.requested_by.groups.all() if retest.requested_by else []
   if any(g.name == 'MANAGEMENT_TEST' for g in requestor_groups):
       recipients.extend(['fm_test@kapa-oil.com', 'hod_test@kapa-oil.com', 'qao@kapa-oil.com'])
   elif any(g.name == 'FM_TEST' for g in requestor_groups):
       recipients.extend(['hod_test@kapa-oil.com', 'qao@kapa-oil.com'])
   elif any(g.name == 'HOD_TEST' for g in requestor_groups):
       recipients.extend(['qao@kapa-oil.com'])

   # Remove duplicates while preserving order
   recipients = list(dict.fromkeys(recipients))

   try:
       send_mail(
           subject=subject,
           message=message,
           from_email='kapaportal@kapa-oil.local',
           recipient_list=recipients,
           fail_silently=True
       )
       logger.info(f"Retest completion notification email sent successfully for RMTR {report.rmtr_no}")
   except Exception as e:
       logger.error(f"Failed to send retest completion notification email: {str(e)}")






logger = logging.getLogger(__name__)
@login_required
def qao_test_approval(request, rmtr_no):
    try:
        # Fetch the report
        report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)

        # Permission check
        if not request.user.groups.filter(name__in=['QAO', 'ADMIN']).exists():
            messages.error(request, 'You do not have permission to access this page.')
            logger.warning(f"Permission denied for user {request.user.username}.")
            return redirect('pending')

        if request.method == 'POST':
            # Handle image upload if present
            if 'test_image' in request.FILES:
                try:
                    # Delete old image if it exists and isn't the default
                    if report.test_image and 'default.jpg' not in report.test_image.name:
                        try:
                            report.test_image.delete(save=False)
                        except Exception as e:
                            logger.warning(f"Failed to delete old image for RMTR {rmtr_no}: {str(e)}")
                    
                    # Save new image
                    report.test_image = request.FILES['test_image']
                    report.save()
                    
                    logger.info(f"Successfully updated test image for RMTR {rmtr_no}")
                    return JsonResponse({
                        'success': True,
                        'message': 'Test image updated successfully',
                        'image_url': report.test_image.url
                    })
                except Exception as img_error:
                    logger.error(f"Error updating test image for RMTR {rmtr_no}: {str(img_error)}")
                    return JsonResponse({
                        'success': False,
                        'message': 'Failed to update test image'
                    }, status=500)

            # Handle approval process
            approval_status = request.POST.get('approval_status')
            comments = request.POST.get('comments', '').strip()
            current_time = timezone.now()

            # Validate approval_status
            if not approval_status or approval_status not in ['approved', 'rejected']:
                logger.error("Invalid approval status provided.")
                return JsonResponse({'success': False, 'message': 'Invalid approval status'}, status=400)

            logger.info(f"Processing QAO approval for RMTR {rmtr_no} with status: {approval_status}.")

            try:
                with transaction.atomic():
                    # Update report based on the action
                    if approval_status == 'approved':
                        report.qao_approved = True
                        report.qao_rejected = False
                        report.qao_date_approved = current_time
                        report.status = 'Pending: HOD Test Approval'
                    elif approval_status == 'rejected':
                        report.qao_approved = False
                        report.qao_rejected = True
                        report.qao_date_rejected = current_time
                        # Modified: Continue to next stage instead of marking as rejected
                        report.status = 'Pending: HOD Test Approval'

                    report.qao_comments = comments
                    report.save()

                # Get notification emails based on plant
                try:
                    plant = Plant.objects.get(name=report.plant)
                    recipients = plant.get_notification_emails()
                    if request.user.email:
                        recipients.append(request.user.email)
                except Plant.DoesNotExist:
                    recipients = ['ict@kapa-oil.com']
                    logger.warning(f"Plant not found for {report.plant}, using default email")

                # Send email notification
                try:
                    subject = f'RMTR {rmtr_no} - QAO {approval_status.title()} the Test Results '
                    
                    # Update message content to reflect that process continues despite rejection
                    message_status = "Approved" if approval_status == "approved" else "Rejected "
                    
                    message = f"""
                    RMTR Details:
                    -------------
                    RMTR Number: {rmtr_no}

                    Status: {message_status}

                    Material: {report.material_type}

                    Supplier: {report.supplier}

                    Plant: {report.plant}
                    
                    QAO Comments: {comments}
                    
                    Action By: {request.user.get_full_name() or request.user.username}
                    Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                    Raw Material Test Report Link: http://10.0.0.7:8020
                    """

                    send_mail(
                        subject=subject,
                        message=message,
                        from_email='kapaportal@kapa-oil.local',
                        recipient_list=recipients,
                        fail_silently=True,
                    )
                    logger.info(f"Email sent successfully for RMTR {rmtr_no} to {recipients}")
                except Exception as email_error:
                    logger.error(f"Failed to send email for RMTR {rmtr_no}: {str(email_error)}")

                return JsonResponse({
                    'success': True, 
                    'message': f'Request {approval_status} successfully.', 
                    'redirect_url': '/pending/'
                })

            except Exception as db_error:
                logger.error(f"Database error while processing QAO approval for RMTR {rmtr_no}: {str(db_error)}")
                return JsonResponse({
                    'success': False, 
                    'message': 'An error occurred while processing the request.'
                }, status=500)

        # Render template for GET request
        context = {
            'report': report,
            'page_title': 'QAO Test Approval'
        }
        return render(request, 'qao_test_approval.html', context)

    except Exception as e:
        logger.exception(f"Error in QAO test approval view for RMTR {rmtr_no}: {str(e)}")
        messages.error(request, 'An unexpected error occurred. Please try again.')
        return redirect('pending')
    
    
# Works okay 12/23/24
# Update bypasses the management test if there is only one approver
""""""
def hod_test_approval(request, rmtr_no):
    try:
        report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)
        
        # Check permissions
        if not request.user.groups.filter(name__in=['HOD','HOD_TEST','ADMIN']).exists():
            messages.error(request, 'You do not have permission to access this page')
            return redirect('pending')

        if request.method == 'POST':
            status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            current_time = timezone.now()

            # Validate status
            if status not in ['approved', 'rejected']:
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid approval status'
                }, status=400)

            # Update the RMTRRequest model directly
            if status == 'approved':
                report.hod_test_approved = True
                report.hod_test_rejected = False
                report.status = 'Pending: FM Test Approval'
                report.hod_test_date_approved = current_time
                report.hod_test_date_rejected = None
            else:  # rejected
                report.hod_test_approved = False
                report.hod_test_rejected = True
                report.status = 'Pending: FM Test Approval'
                report.hod_test_date_approved = None
                report.hod_test_date_rejected = current_time

            report.hod_test_comments = comments
            report.save()

            # Send email 
            try:
                # Define recipients list - you can modify this as needed
                recipients = [
                    'fm@kapa-oil.com',
                    'kishore@kapa-oil.com',
                    'ict@kapa-oil.com',
                   
                    
                    request.user.email,
                    
                ]

               
                subject = f'RMTR {rmtr_no} - HOD {report.plant.name} Test {"Approval" if status == "approved" else "Rejection"}'
                message = f"""
                RMTR Details:
                -------------
                RMTR Number: {rmtr_no}

                Status: {status.title()}

                Material: {report.material_type}

                Supplier: {report.supplier}
                
                HOD Test Comments: {comments}  
                
                
                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                Raw Material Test Report Link: http://10.0.0.7:8020
                """                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=False
                )

            except Exception as e:
                logger.error(f"Failed to send email for RMTR {rmtr_no}: {str(e)}")
                # email fail safe and procedure goes on still.
                
            return JsonResponse({
                'success': True,
                'message': f'Request {status} successfully'
            })

        # GET request
        context = {
            'report': report,
            'page_title': 'HOD Test Approval',
            'can_approve': not report.hod_test_approved,
            'can_reject': not report.hod_test_rejected
        }
        return render(request, 'hod_test_approval.html', context)

    except Exception as e:
        logger.error(f"Error in hod_test_approval: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'An error occurred while processing your request'
        }, status=500)
    




@login_required
def fm_test_approval(request, rmtr_no):
    try:
        report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)
        
        # Check permissions
        if not request.user.groups.filter(name__in=['FM', 'FM_TEST', 'ADMIN']).exists():
            messages.error(request, 'You do not have permission to access this page')
            return redirect('pending')

        if request.method == 'POST':
            # Handle image upload if present
            if 'test_image' in request.FILES:
                try:
                    # Delete old image 
                    if report.test_image and 'default.jpg' not in report.test_image.name:
                        try:
                            report.test_image.delete(save=False)
                        except Exception as e:
                            logger.warning(f"Failed to delete old image for RMTR {rmtr_no}: {str(e)}")
                    
                    # Save new image
                    report.test_image = request.FILES['test_image']
                    report.save()
                    
                    logger.info(f"Successfully updated test image for RMTR {rmtr_no}")
                    return JsonResponse({
                        'success': True,
                        'message': 'Test image updated successfully',
                        'image_url': report.test_image.url
                    })
                except Exception as img_error:
                    logger.error(f"Error updating test image for RMTR {rmtr_no}: {str(img_error)}")
                    return JsonResponse({
                        'success': False,
                        'message': 'Failed to update test image'
                    }, status=500)

            # Handle approval process
            status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            current_time = timezone.now()

            # Update report status
            if status == 'approved':
                report.fm_test_approved = True
                report.fm_test_rejected = False
                report.fm_test_date_approved = current_time
                report.fm_test_date_rejected = None

                # Check if there's a second approver
                if report.second_approver:
                    # Go to management test approval
                    report.status = 'Pending: Management Test Approval'
                else:
                
                    report.status = 'Pending: Milan Approval'
                   
                    report.management_test_approved = True
                    report.management_test_date_approved = current_time
            else:
                #Test Rejection
                report.fm_test_approved = False
                report.fm_test_rejected = True
                report.fm_test_date_approved = None
                report.fm_test_date_rejected = current_time
                
                
                if report.second_approver:
                    report.status = 'Pending: Management Test Approval'
                else:
                    report.status = 'Pending: Milan Approval'
                    
                    report.management_test_approved = True
                    report.management_test_date_approved = current_time

            report.fm_test_comments = comments
            report.save()

            # Send email notification
            try:
                # Base recipients
                #recipients = ['support.user5@kapa-oil.com']
                recipients = ['ict@kapa-oil.com']
                
                if request.user.email:
                    recipients.append(request.user.email)

                # recipients based on flow
                if report.second_approver:
                    #  management test recipients
                    recipients.extend([
                        'jaivin@kapa-oil.com',
                        'neev@kapa-oil.com'
                    ])
                else:
                    # milan if no management approval required
                    recipients.append('milan@kapa-oil.com')
                
                # Remove duplicates 
                recipients = list(dict.fromkeys(recipients))
                
                next_stage = "Management Test Approval" if report.second_approver else "Milan Approval"
                
               
                message_status = "Approved" if status == "approved" else "Rejected "
                
                subject = f'RMTR {rmtr_no} - FM Test {"Approval" if status == "approved" else "Rejection"}'
                message = f"""
                RMTR Details:
                -------------
                RMTR Number: {rmtr_no}

                Status: {message_status}

                Material: {report.material_type}

                Supplier: {report.supplier}
                
                FM Test Comments: {comments}
                
                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                Next Stage: {next_stage}

                Raw Material Test Report Link: http://10.0.0.7:8020
                """
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=False
                )
                logger.info(f"Email notification sent for RMTR {rmtr_no}")
                
            except Exception as e:
                logger.error(f"Failed to send email for RMTR {rmtr_no}: {str(e)}")
                # Continue execution even if email fails

            return JsonResponse({
                'success': True,
                'message': f'Request {status} successfully. Process will continue to {next_stage}.',
                'status': report.status,
                'redirect_url': '/pending/'
            })

        # GET request
        context = {
            'report': report,
            'page_title': 'FM Test Approval',
            'can_approve': not report.fm_test_approved,
            'can_reject': not report.fm_test_rejected,
            'user_groups': ','.join(request.user.groups.values_list('name', flat=True))
        }
        return render(request, 'fm_test_approval.html', context)

    except Exception as e:
        logger.error(f"Error in fm_test_approval: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'POST':
            return JsonResponse({
                'success': False,
                'message': 'An error occurred while processing your request'
            }, status=500)
        else:
            messages.error(request, 'An error occurred while processing your request')
            return redirect('pending')
      
        
        

        

@login_required
def management_test_approval(request, rmtr_no):
    try:
        report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)
        
        # Check permissions
        if not request.user.groups.filter(name__in=['MANAGEMENT', 'MANAGEMENT_TEST', 'ADMIN']).exists():
            messages.error(request, 'You do not have permission to access this page')
            return redirect('pending')
        
        if request.method == 'POST':
            status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            current_time = timezone.now()
            
            if status == 'approved':
                report.management_test_approved = True
                report.management_test_rejected = False
                report.status = 'Pending: Milan Approval'
                report.management_test_date_approved = current_time
                report.management_test_date_rejected = None
            else:  # rejected
                report.management_test_approved = False
                report.management_test_rejected = True
                
                report.status = 'Pending: Milan Approval'  
                report.management_test_date_approved = None
                report.management_test_date_rejected = current_time
            
            report.management_test_comments = comments
            report.save()
            
            # Send email notification
            try:
                recipients = ['ict@kapa-oil.com',
                'milan@kapa-oil.com',   
                          
                request.user.email
                ]
                
                subject = f'RMTR {rmtr_no} - Management Test {"Approval" if status == "approved" else "Rejection"}'
                
                # Update the message to indicate that the process is continuing despite rejection
                message_status = "Approved" if status == "approved" else "Rejected "
                
                message = f"""
                RMTR Details:
                -------------
                RMTR Number: {rmtr_no}

                Status: {message_status}

                Material Name: {report.material_name}

                Material Type: {report.material_type}

                Supplier: {report.supplier}

                Plant: {report.plant.name if report.plant else 'N/A'}
                
                Management Test Comments: {comments}
                
                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                 Raw Material Test Report Link: http://10.0.0.7:8020
                """
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=False
                )
                logger.info(f"Email notification sent for RMTR {rmtr_no}")
                
            except Exception as e:
                logger.error(f"Failed to send email for RMTR {rmtr_no}: {str(e)}")
                # Continue execution even if email fails
            
            return JsonResponse({
                'success': True,
                'message': f'Request {status} successfully. Process will continue to next approver.',
                'status': report.status,
                'redirect_url': '/pending/'
            })
        
        # GET request
        context = {
            'report': report,
            'page_title': 'Management Test Approval',
            'can_approve': not report.management_test_approved,
            'can_reject': not report.management_test_rejected,
            'user_groups': ','.join(request.user.groups.values_list('name', flat=True))
        }
        return render(request, 'management_test_approval.html', context)
        
    except Exception as e:
        logger.error(f"Error in management_test_approval: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'POST':
            return JsonResponse({
                'success': False,
                'message': 'An error occurred while processing your request'
            }, status=500)
        else:
            messages.error(request, 'An error occurred while processing your request')
            return redirect('pending')
        



        

logger = logging.getLogger(__name__)

@login_required
def milan_approval(request, rmtr_no):
    
    try:
        logger.info(f"Accessing milan_approval for RMTR {rmtr_no}")
        report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)
        
        # Check user permissions
        user_groups = list(request.user.groups.values_list('name', flat=True))
        logger.info(f"User {request.user.username} groups: {user_groups}")
        
        if not request.user.groups.filter(name__in=['MILAN', 'ADMIN']).exists():
            logger.warning(f"User {request.user.username} denied access - insufficient permissions")
            messages.error(request, 'You do not have permission to access this page')
            return redirect('pending')
            
      
        if request.method == 'POST':
            status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            current_time = timezone.now()
            
            # Validate status
            if status not in ['approved', 'rejected']:
                logger.error(f"Invalid approval status received: {status}")
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid approval status'
                }, status=400)
            
            # Update report status and fields
            if status == 'approved':
                report.milan_approved = True
                report.milan_rejected = False
                report.status = 'completed'
                report.milan_date_approved = current_time
                report.milan_date_rejected = None
            else:  # rejected
                report.milan_approved = False
                report.milan_rejected = True
                report.status = 'rejected'
                report.milan_date_approved = None
                report.milan_date_rejected = current_time
            
            report.milan_comments = comments
            report.save()
            
            # Send email notification
            try:
                # Base recipients list
                recipients = [
                     request.user.email,
                    'purchase.user1@kapa-oil.com',
                    'purchase.user2@kapa-oil.com',
                    'purchase.user10@kapa-oil.com',
                    'purchase.user7@kapa-oil.com',
                    'purchase.user9@kapa-oil.com',
                    'purchase.user5@kapa-oil.com',
                    'purchase.user4@kapa-oil.com',
                    'jaivin@kapa-oil.com',
                    'qao.user6@kapa-oil.com',
                    'qao.user47@kapa-oil.com',
                    'ict@kapa-oil.com',
                    'fm@kapa-oil.com',
                    'kishore@kapa-oil.com',
                    'purchase.user3@kapa-oil.com',
                    'purchase@kapa-oil.com',
                    'development.user1@kapa-oil.com',
                    'development.user2@kapa-oil.com'
                                     
                ]

                # Plant-specific recipients(HODs)
                if report.plant:
                    try:
                      
                        plant_emails = report.plant.get_notification_emails()
                        
                     
                        if hasattr(report.plant, 'hod_email') and report.plant.hod_email:
                            recipients.append(report.plant.hod_email)
                            logger.info(f"Added HOD email for plant {report.plant.name}: {report.plant.hod_email}")
                            
                    
                        if hasattr(report.plant, 'deputy_hod_email') and report.plant.deputy_hod_email:
                            recipients.append(report.plant.deputy_hod_email)
                            logger.info(f"Added Deputy HOD email for plant {report.plant.name}: {report.plant.deputy_hod_email}")
                            
                        
                        recipients.extend(plant_emails)
                        logger.info(f"Added plant notification emails for {report.plant.name}")
                        
                    except Exception as e:
                        logger.error(f"Error getting plant-specific recipients for plant {report.plant.name}: {str(e)}")
                        
                
                # Remove duplicates 
                recipients = list(dict.fromkeys(filter(None, recipients)))
                logger.info(f"Final recipient list for RMTR {rmtr_no}: {recipients}")
                
                subject = f'RMTR {rmtr_no} - Milan Test {"Approval" if status == "approved" else "Rejection"}'
                message = f"""
                RMTR Details:
                -------------
                RMTR Number: {rmtr_no}

                Status: {status.title()}

                Material Name: {report.material_name}

                Material Type: {report.material_type}

                Supplier: {report.supplier}

                Plant: {report.plant.name if report.plant else 'N/A'}
                
                Mr. Milan's Comments: {comments}
                

                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                Raw Material Test Report Link: http://10.0.0.7:8020
                """
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=False
                )
                logger.info(f"Email notification sent for RMTR {rmtr_no} to {len(recipients)} recipients")
                
            except Exception as e:
                logger.error(f"Failed to send email for RMTR {rmtr_no}: {str(e)}")
                # Continue execution even if email fails
            
            return JsonResponse({
                'success': True,
                'message': f'Request {status} successfully'
            })

        # GET request 
        context = {
            'report': report,
            'page_title': 'Milan Approval',
            'can_approve': not report.milan_approved,
            'can_reject': not report.milan_rejected,
            'user_groups': ','.join(user_groups)
        }
        return render(request, 'milan_approval.html', context)

    except Exception as e:
        logger.exception(f"Error in milan_approval view for RMTR {rmtr_no}: {str(e)}")
        messages.error(request, 'An error occurred while processing your request')
        return redirect('pending')


        
@login_required
def process_approval(request, rmtr_no):
    try:
        # Get RMTR request
        rmtr_request = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)
        
        # Get user role
        user_role = request.user.groups.first().name if request.user.groups.exists() else None
        
        if not user_role:
            return JsonResponse({
                'status': 'error',
                'message': 'User has no assigned role'
            }, status=403)

        if request.method == 'POST':
            try:
                # Get approval data
                approved = request.POST.get('approval_status') == 'approved'
                comments = request.POST.get('comments', '')
                priority = request.POST.get('priority', '')  
                sensitivity = request.POST.get('sensitivity', '')  

                # Get the appropriate approval model
                ApprovalModel = APPROVAL_MODELS.get(user_role)
                if not ApprovalModel:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Invalid role: {user_role}'
                    }, status=400)

                # Create or update approval record
                approval, created = ApprovalModel.objects.get_or_create(
                    request=rmtr_request,
                    defaults={
                        'approved': approved,
                        'rejected': not approved,
                        'comments': comments,
                    }
                )

                if not created:
                    approval.approved = approved
                    approval.rejected = not approved
                    approval.comments = comments

                # Add role-specific fields
                if user_role == 'HOD_PURCHASE':
                    approval.priority = priority
                    approval.sensitivity = sensitivity

                # Set approval/rejection date
                if approved:
                    approval.date_approved = timezone.now()
                else:
                    approval.date_rejected = timezone.now()

                approval.save()

                # Update RMTR status
                new_status = RMTRStatusManager.get_next_status(rmtr_request.status, approved)
                rmtr_request.status = new_status
                rmtr_request.save()

                # Send notification
                NotificationService.send_approval_notification(
                    request=rmtr_request,
                    stage_name=user_role,
                    is_approved=approved,
                    comments=comments
                )

                return JsonResponse({
                    'status': 'success',
                    'message': f'Request {rmtr_no} {"approved" if approved else "rejected"} successfully'
                })

            except Exception as e:
                logger.error(f"Error processing approval for RMTR {rmtr_no}: {str(e)}", exc_info=True)
                return JsonResponse({
                    'status': 'error',
                    'message': 'An error occurred while processing the approval'
                }, status=500)

        # GET request - render appropriate template
        template_mapping = {
            'HOD_PURCHASE': 'hod_purchase_approval.html',
            'MANAGEMENT': 'management_approval.html',
            'FM': 'fm_approval.html',
            
        }

        template_name = template_mapping.get(user_role)
        if not template_name:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid role'
            }, status=400)

        context = {
            'report': rmtr_request,
            'user_role': user_role,
            'can_approve': True  
        }

        return render(request, template_name, context)

    except Exception as e:
        logger.error(f"General error in process_approval: {str(e)}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': 'An unexpected error occurred'
        }, status=500)


logger = logging.getLogger(__name__)

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            messages.success(request, 'Successfully logged in!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password. Please try again.')
    
    return render(request, 'login.html')







def fetch_material_data(request):
    # Query all materials, their subcategories, and tests
    materials = Material.objects.prefetch_related('subcategories__tests').all()

    # Prepare the response structure
    materials_data = []
    
    for material in materials:
        material_dict = {
            'material': material.name,
            'subcategories': []
        }
        
        for subcategory in material.subcategories.all():
            subcategory_dict = {
                'name': subcategory.name,
                'tests': [tests.name for tests in subcategory.tests.all()]  # List of tests for each subcategory
            }
            material_dict['subcategories'].append(subcategory_dict)
        
        materials_data.append(material_dict)

    return JsonResponse({'materials': materials_data})


def test(request):
    all_reports = RMTRRequest.objects.all()
    logger.info(all_reports)  # This will log all the report data in the console or log file
    return render(request, 'pending.html', {'pending_reports': all_reports})
  






logger = logging.getLogger(__name__)

@login_required 
def completed_reports(request):
    """Display completed RMTRs with all test details"""
    try:
        # Get all completed reports with related data
        completed_rmtrs = RMTRRequest.objects.filter(
            Q(status__iexact='completed') |
            Q(status__iexact='rejected')
        ).select_related(
            'supplier',
            'plant'
        )
        
        # Convert to list and sort
        completed_rmtrs = sorted(
            completed_rmtrs,
            key=lambda x: (
                int(x.rmtr_no.split('-')[0]),  # Year part
                int(x.rmtr_no.split('-')[1])   # Number part
            ),
            reverse=True
        )
        
        # Process the reports to include all required fields
        completed_reports = []
        for report in completed_rmtrs:
            report_data = {
                'rmtr_no': report.rmtr_no,
                'material_name': report.material_name,
                'material_type': report.material_type,
                'sub_category': report.sub_category,
                'tests_carried_out': report.tests,
                'raw_material_results': _format_results(report.raw_material_results),
                'kapa_standards': _format_standards(report.specs),
                'sample_results': _format_results(report.sample_results),
                'supplier': report.supplier.name if report.supplier else 'N/A',
                'plant': report.plant.name if report.plant else 'N/A',
                'date': report.management_test_date_approved or report.date_created,
                'status': report.status,
                'qao_comments': report.qao_comments if hasattr(report, 'qao_comments') else '',
                'management_test_date_approved': report.management_test_date_approved.strftime('%Y-%m-%d') if report.management_test_date_approved else 'N/A'
            }
            completed_reports.append(report_data)
        
        context = {
            'completed_reports': completed_reports,  # Send ALL completed reports
            'user_role': request.user.groups.first().name if request.user.groups.exists() else None,
            'title': 'Completed RMTRs'
        }
        
        logger.info(f"Successfully loaded {len(completed_reports)} completed reports")
        return render(request, 'completed_reports.html', context)
    
    except Exception as e:
        logger.error(f"Error in completed_reports view: {str(e)}")
        messages.error(request, 'Error loading completed reports')
        return redirect('dashboard')

def _format_results(results):
    """Format test results for display"""
    if not results:
        return 'No results available'
    
    try:
        if isinstance(results, str):
            # If results are stored as string, return as is
            return results
        elif isinstance(results, dict):
            # If results are stored as dictionary, format them
            return ', '.join([f"{k}: {v}" for k, v in results.items()])
        elif isinstance(results, list):
            # If results are stored as list, join them
            return ', '.join(results)
        else:
            return str(results)
    except Exception as e:
        logger.error(f"Error formatting results: {str(e)}")
        return 'Error formatting results'

def _format_standards(standards):
    """Format Kapa standards for display"""
    if not standards:
        return 'No standards available'
    
    try:
        if isinstance(standards, str):
            return standards
        elif isinstance(standards, dict):
            return ', '.join([f"{k}: {v}" for k, v in standards.items()])
        else:
            return str(standards)
    except Exception as e:
        logger.error(f"Error formatting standards: {str(e)}")
        return 'Error formatting standards'




def upload_rmtr_image(request):
    if request.method == 'POST':
        form = RMTRRequestForm(request.POST, request.FILES)
        if form.is_valid():
            # Save the RMTR form data and image
            rmtr = form.save(commit=False)  # Don't commit yet to customize it

            # You can optionally customize the file upload path here if needed
            # For example, setting the image file name based on the rmtr_no field:
            if rmtr.rmtr_no:
                rmtr.image.name = f"rmtr_{rmtr.rmtr_no}/{rmtr.image.name.split('/')[-1]}"
            
            rmtr.save()  # Now save the RMTR object, which includes the image

            return JsonResponse({'message': 'Image uploaded successfully!'}, status=201)
        else:
            return JsonResponse({'message': 'Error uploading image', 'errors': form.errors}, status=400)
    else:
        form = RMTRRequestForm()

    return render(request, 'test_request.html', {'form': form})
""""
@login_required
def submit_form(request):
    #Handle form submission for RMTR requests
    logger.info("Processing form submission")
    
    if request.method != 'POST':
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid request method'
        }, status=405)

    try:
        form = RMTRRequestForm(request.POST, request.FILES)
        
        if not form.is_valid():
            logger.error(f"Form validation failed: {form.errors}")
            return JsonResponse({
                'status': 'error',
                'message': 'Form validation failed',
                'errors': form.errors
            }, status=400)

        with transaction.atomic():
            report = form.save(commit=False)
            
            # Validate supplier
            supplier_instance = form.cleaned_data.get('supplier')
            if not supplier_instance:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Supplier is required.'
                }, status=400)

            # Set report fields
            report.supplier = supplier_instance
            report.requested_by = form.cleaned_data.get('requested-by') or request.user.username
            report.status = 'pending'
            report.sub_category = form.cleaned_data.get('sub_category', '')
            report.approved_mgt = form.cleaned_data.get('approved-mgt')
            report.tests = request.POST.get('selected_tests', '')

            # Generate RMTR number if needed
            if not report.rmtr_no:
                report.rmtr_no = report.generate_next_rmtr_no()

            # Save report
            report.save()
            logger.info(f"Successfully created RMTR: {report.rmtr_no}")

            # Send notification
            try:
                recipients = [request.user.email, 
                              
                              'ict@kapa-oil.com'
                              
                              ]
                # Get HOD Purchase email if configured
                hod_email = getattr(settings, 'HOD_PURCHASE_EMAIL', None)
                if hod_email:
                    recipients.append(hod_email)

                send_mail(
                    subject='New RMTR Request Created',
                    message=f'''
                    RMTR report {report.rmtr_no} has been created.
                    Date: {report.date}
                    Created by: {report.requested_by}
                    Supplier: {report.supplier.name}
                    Material Type: {report.material_type}
                    ''',
                    from_email='kapaportal@kapaoil.com',
                    recipient_list=recipients,
                    fail_silently=True
                )
            except Exception as e:
                logger.warning(f"Email notification failed: {str(e)}")

            return JsonResponse({
                'status': 'success',
                'message': 'RMTR created successfully',
                'rmtr_no': report.rmtr_no,
                'redirect': '/dashboard/'
            })

    except Exception as e:
        logger.error(f"Error in submit_form: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Server error occurred while processing your request'
        }, status=500)
"""

def create_report(request):
    # Check if RMTR No. is already stored in the session
    if 'rmtr_no' not in request.session:
        # Create a new instance to generate the next RMTR number
        new_request = RMTRRequest()
        next_rmtr_no = new_request.generate_next_rmtr_no()  # Generate RMTR number
        request.session['rmtr_no'] = next_rmtr_no  # Store in session

    # Fetch RMTR No. from the session
    rmtr_no = request.session['rmtr_no']

    # Handle POST request (form submission)
    if request.method == 'POST':
        form = RMTRRequestForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)  # Create report instance
            report.rmtr_no = rmtr_no  # Assign the RMTR number
            report.created_by = request.user  # Assign the creator

            try:
                # Save the report instance
                report.save()

                # Clear RMTR number from session after save
                del request.session['rmtr_no']

                # Send success response
                return JsonResponse({
                    'status': 'success',
                    'message': 'Report created successfully!',
                    'redirect': '/dashboard/',  # Redirect after success
                })

            except Exception as e:
                # Return an error response
                return JsonResponse({
                    'status': 'error',
                    'message': f'Error creating report: {str(e)}',
                }, status=500)

        else:
            # Handle invalid form errors
            return JsonResponse({
                'status': 'error',
                'message': 'Form is invalid.',
                'errors': form.errors.as_json(),
            }, status=400)

    # Render the form and RMTR No. for GET request
    return render(request, 'test_request.html', {'form': RMTRRequestForm(), 'rmtr_no': rmtr_no})

# Fetch plant and HOD
def plant_hod_data(request):
    plants = Plant.objects.all().values('id', 'name', 'hod')
    plant_hod_mapping = list(plants)
    return JsonResponse(plant_hod_mapping, safe=False)




# Test Results Submission View
def submit_test_results(request, rmtr_no):
    report = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)

    if request.method == 'POST':
        form = TestResultsForm(request.POST)
        if form.is_valid():
            test_result = form.save(commit=False)
            test_result.report = report
            test_result.save()

            # Update RMTRRequest status
            report.status = 'Test Done'
            report.save()

            # Send email notification
            send_mail(
                subject='Test Results Submitted',
                message=f'The test results for RMTR request {rmtr_no} have been submitted.',
                from_email='your_email@example.com',
                recipient_list=[report.created_by.email],
                fail_silently=False,
            )

            messages.success(request, 'Test results submitted successfully.')
            return redirect('next_stage_view')  # Redirect to the next approval stage

    else:
        form = TestResultsForm()

    return render(request, 'fill_page.html', {'form': form, 'report': report})









logger = logging.getLogger(__name__)

@login_required
def completed_reports(request):
    """View for completed RMTR reports with filtering and export capabilities"""
    try:
        # Get filter parameters
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        material_type = request.GET.get('material_type')
        search_query = request.GET.get('search')
        export_format = request.GET.get('export')

        # Base query for completed and rejected reports
        completed_rmtrs = RMTRRequest.objects.filter(
            Q(status__iexact='completed') | 
            Q(status__iexact='rejected')
        ).select_related(
            'supplier',
            'plant'
        ).order_by('-date')

        # Apply filters
        if date_from:
            completed_rmtrs = completed_rmtrs.filter(date__gte=date_from)
        if date_to:
            completed_rmtrs = completed_rmtrs.filter(date__lte=date_to)
        if material_type:
            completed_rmtrs = completed_rmtrs.filter(material_type=material_type)
        if search_query:
            completed_rmtrs = completed_rmtrs.filter(
                Q(rmtr_no__icontains=search_query) |
                Q(material_type__icontains=search_query) |
                Q(sub_category__icontains=search_query) |
                Q(supplier__name__icontains=search_query) |
                Q(tests_carried_out__icontains=search_query) |
                Q(raw_material_results__icontains=search_query)
            )

        # Handle exports
        if export_format == 'excel':
            return export_to_excel(completed_rmtrs)
        elif export_format == 'pdf':
            report_id = request.GET.get('rmtr_no')
            if report_id:
                report = completed_rmtrs.get(rmtr_no=report_id)
                return generate_rmtr_pdf(report)

        # Get distinct material types for filtering
        material_types = RMTRRequest.objects.filter(
            Q(status__iexact='completed') | 
            Q(status__iexact='rejected')
        ).values_list('material_type', flat=True).distinct()

        context = {
            'completed_reports': completed_rmtrs,  # Send ALL reports to the template
            'material_types': material_types,
            'filters': {
                'date_from': date_from,
                'date_to': date_to,
                'material_type': material_type,
                'search': search_query
            },
            'total_reports': completed_rmtrs.count(),
        }

        return render(request, 'completed_reports.html', context)

    except Exception as e:
        logger.error(f"Error in completed_reports view: {str(e)}")
        messages.error(request, 'Error loading completed reports')
        return redirect('dashboard')


def export_to_excel(queryset):
    """Export completed reports to Excel with all fields"""
    try:
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Completed RMTRs')

        # Styles
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#3A6D8C',
            'color': 'white',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True
        })

        cell_format = workbook.add_format({
            'border': 1,
            'align': 'left',
            'valign': 'vcenter',
            'text_wrap': True
        })

        date_format = workbook.add_format({
            'border': 1,
            'align': 'left',
            'valign': 'vcenter',
            'num_format': 'dd/mm/yyyy'
        })

        # Set column widths (adjusted for all columns)
        worksheet.set_column('A:A', 15)   # RMTR No
        worksheet.set_column('B:B', 12)   # Date Created
        worksheet.set_column('C:C', 25)   # Supplier
        worksheet.set_column('D:D', 20)   # Material Name
        worksheet.set_column('E:E', 15)   # Plant
        worksheet.set_column('F:F', 30)   # Justification
        worksheet.set_column('G:G', 30)   # Specs
        worksheet.set_column('H:H', 12)   # Status
        worksheet.set_column('I:I', 20)   # Material Type
        worksheet.set_column('J:J', 20)   # Sub Category
        worksheet.set_column('K:K', 30)   # Tests Carried Out
        worksheet.set_column('L:L', 30)   # Raw Material Results
        worksheet.set_column('M:M', 30)   # KAPA Standards
        worksheet.set_column('N:N', 30)   # Sample Results
        worksheet.set_column('O:O', 20)   # Requested By
        worksheet.set_column('P:P', 12)   # Quantity
        worksheet.set_column('Q:Q', 12)   # UOM
        worksheet.set_column('R:R', 30)   # Lab QC Comments
        worksheet.set_column('S:S', 30)   # QAO Comments
        worksheet.set_column('T:T', 30)   # HOD Test Comments
        worksheet.set_column('U:U', 30)   # FM Test Comments
        worksheet.set_column('V:V', 30)   # Management Test Comments
        worksheet.set_column('W:W', 30)   # Milan Comments

        # Define all headers matching the HTML checkboxes order
        headers = [
            'RMTR No',                      # 0
            'Date Created',                 # 1
            'Supplier',                     # 2
            'Material Name',                # 3
            'Plant',                        # 4
            'Justification',                # 5
            'Specs',                        # 6
            'Status',                       # 7
            'Material Type',                # 8
            'Sub Category',                 # 9
            'Tests Carried Out',            # 10
            'Raw Material Results',         # 11
            'KAPA Standards',               # 12
            'Sample Results',               # 13
            'Requested By',                 # 14
            'Quantity',                     # 15
            'UOM',                          # 16
            'Lab QC Comments',              # 17
            'QAO Comments',                 # 18
            'HOD Test Comments',            # 19
            'FM Test Comments',             # 20
            'Management Test Comments',     # 21
            'Milan Comments'                # 22
        ]

        # Write headers
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)

        # Write data
        for row, report in enumerate(queryset, start=1):
            col = 0
            
            # RMTR No
            worksheet.write(row, col, report.rmtr_no, cell_format)
            col += 1
            
            # Date Created
            worksheet.write(row, col, report.date, date_format)
            col += 1
            
            # Supplier
            worksheet.write(row, col, report.supplier.name if report.supplier else 'N/A', cell_format)
            col += 1
            
            # Material Name
            worksheet.write(row, col, getattr(report, 'material_name', 'N/A'), cell_format)
            col += 1
            
            # Plant
            worksheet.write(row, col, report.plant.name if report.plant else 'N/A', cell_format)
            col += 1
            
            # Justification
            worksheet.write(row, col, getattr(report, 'justification', ''), cell_format)
            col += 1
            
            # Specs
            worksheet.write(row, col, getattr(report, 'specs', ''), cell_format)
            col += 1
            
            # Status
            worksheet.write(row, col, report.status.title(), cell_format)
            col += 1
            
            # Material Type
            worksheet.write(row, col, report.material_type, cell_format)
            col += 1
            
            # Sub Category
            worksheet.write(row, col, report.sub_category, cell_format)
            col += 1

            # Combine all test results for this report
            all_tests = []
            all_raw_results = []
            all_kapa_standards = []
            all_sample_results = []

            # Loop through test fields 1-16
            for i in range(1, 17):
                tests_carried = getattr(report, f'tests_carried_out{i}', '')
                if tests_carried:
                    all_tests.append(tests_carried)
                    all_raw_results.append(getattr(report, f'raw_material_results{i}', ''))
                    all_kapa_standards.append(getattr(report, f'kapa_standards{i}', ''))
                    all_sample_results.append(getattr(report, f'sample_results{i}', ''))

            # Tests Carried Out
            worksheet.write(row, col, '\n'.join(filter(None, all_tests)), cell_format)
            col += 1
            
            # Raw Material Results
            worksheet.write(row, col, '\n'.join(filter(None, all_raw_results)), cell_format)
            col += 1
            
            # KAPA Standards
            worksheet.write(row, col, '\n'.join(filter(None, all_kapa_standards)), cell_format)
            col += 1
            
            # Sample Results
            worksheet.write(row, col, '\n'.join(filter(None, all_sample_results)), cell_format)
            col += 1
            
            # Requested By
            worksheet.write(row, col, getattr(report, 'requested_by', ''), cell_format)
            col += 1
            
            # Quantity
            worksheet.write(row, col, str(getattr(report, 'quantity', '')), cell_format)
            col += 1
            
            # UOM
            worksheet.write(row, col, getattr(report, 'uom', ''), cell_format)
            col += 1
            
            # Lab QC Comments
            worksheet.write(row, col, getattr(report, 'lab_qc_comments', ''), cell_format)
            col += 1
            
            # QAO Comments
            worksheet.write(row, col, getattr(report, 'qao_comments', ''), cell_format)
            col += 1
            
            # HOD Test Comments
            worksheet.write(row, col, getattr(report, 'hod_test_comments', ''), cell_format)
            col += 1
            
            # FM Test Comments
            worksheet.write(row, col, getattr(report, 'fm_test_comments', ''), cell_format)
            col += 1
            
            # Management Test Comments
            worksheet.write(row, col, getattr(report, 'management_test_comments', ''), cell_format)
            col += 1
            
            # Milan Comments
            worksheet.write(row, col, getattr(report, 'milan_comments', ''), cell_format)

        # Add autofilter
        worksheet.autofilter(0, 0, queryset.count(), len(headers) - 1)

        # Close the workbook
        workbook.close()

        # Create the response
        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f'Completed_RMTRs_{timezone.now().strftime("%Y%m%d")}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response

    except Exception as e:
        logger.error(f"Error exporting to Excel: {str(e)}")
        raise
@login_required
def get_report_data(request, rmtr_no):
    """API endpoint for getting report details"""
    try:
        report = RMTRRequest.objects.select_related(
            'supplier', 
            'plant'
        ).get(rmtr_no=rmtr_no)

        # Get all necessary data
        data = {
            'rmtr_no': report.rmtr_no,
            'date': report.date.strftime('%Y-%m-%d'),
            'material_type': report.material_type,
            'sub_category': report.sub_category,
            'supplier': report.supplier.name if report.supplier else 'N/A',
            'plant': report.plant.name if report.plant else 'N/A',
            'tests_carried_out': report.tests_carried_out or '',
            'raw_material_results': report.raw_material_results or '',
            'sample_results': report.sample_results or '',
            'kapa_standards': report.kapa_standards or '',
            'status': report.status,
            'requested_by': report.requested_by,
            'justification': report.justification,
            'uom': report.uom,
            'quantity': report.quantity,
            'specs': report.specs,
        }

        # Add approval information if available
        if hasattr(report, 'management_test_date_approved'):
            data['management_test_date_approved'] = (
                report.management_test_date_approved.strftime('%Y-%m-%d') 
                if report.management_test_date_approved else None
            )

        return JsonResponse(data)

    except ObjectDoesNotExist:
        return JsonResponse(
            {'error': 'Report not found'}, 
            status=404
        )
    except Exception as e:
        return JsonResponse(
            {'error': f'Server error: {str(e)}'}, 
            status=500
        )


def process_test_results(report):
    """Process test results into structured format"""
    tests_list = []
    
    # Handle different formats of data storage (comma or newline separated)
    separators = [',', '\n']
    
    def split_field(field):
        if not field:
            return []
        for sep in separators:
            if sep in field:
                return [item.strip() for item in field.split(sep) if item.strip()]
        return [field.strip()]
    
    # Split all fields
    tests = split_field(report.tests_carried_out)
    results = split_field(report.raw_material_results)
    samples = split_field(report.sample_results)
    standards = split_field(report.kapa_standards)
    
    # Get the maximum length of all lists
    max_length = max(len(tests), len(results), len(samples), len(standards))
    
    # Pad shorter lists with N/A
    tests.extend(['N/A'] * (max_length - len(tests)))
    results.extend(['N/A'] * (max_length - len(results)))
    samples.extend(['N/A'] * (max_length - len(samples)))
    standards.extend(['N/A'] * (max_length - len(standards)))
    
    # Combine all results
    for i in range(max_length):
        tests_list.append({
            'test': tests[i],
            'result': results[i],
            'sample': samples[i],
            'standard': standards[i]
        })
    
    return tests_list


class RMTRTestView:
    @staticmethod
    def get_test_data(rmtr_request):
        """Helper method to get all test data from an RMTR request"""
        test_data = []
        
        for i in range(1, 17):  # Your model has 16 sets of test fields
            test_entry = {
                'test_number': i,
                'tests_carried_out': getattr(rmtr_request, f'tests_carried_out{i}', ''),
                'sample_results': getattr(rmtr_request, f'sample_results{i}', ''),
                'raw_material_results': getattr(rmtr_request, f'raw_material_results{i}', ''),
                'kapa_standards': getattr(rmtr_request, f'kapa_standards{i}', '')
            }
            
            # Only include entries that have data
            if any(value for key, value in test_entry.items() if key != 'test_number'):
                test_data.append(test_entry)
                
        return test_data



from django.views.generic import DetailView

class RMTRDetailView(DetailView):
    model = RMTRRequest
    template_name = 'completed_reports.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['test_data'] = RMTRTestView.get_test_data(self.object)
        return context



class RMTRTestSerializer(serializers.ModelSerializer):
    test_data = serializers.SerializerMethodField()
    
    class Meta:
        model = RMTRRequest
        fields = ['id', 'rmtr_no', 'test_data']  # Add other fields as needed
        
    def get_test_data(self, obj):
        return RMTRTestView.get_test_data(obj)


logger = logging.getLogger(__name__)
def get_rmtr_tests(request, rmtr_no):
    """Return structured test and comment information for a given RMTR."""
    try:
        report = RMTRRequest.objects.get(rmtr_no=rmtr_no)

        # tests_to_be_done: prefer explicit field `tests`, fallback to empty string
        tests_to_be_done = getattr(report, 'tests', '') or ''

        # structured tests list using helper
        tests_list = RMTRTestView.get_test_data(report)

        # retest requests related to this RMTR
        retests_qs = getattr(report, 'rmtr_retests', None)
        retests = []
        if retests_qs is not None:
            for r in retests_qs.all().order_by('-requested_at'):
                retests.append({
                    'requested_at': r.requested_at.isoformat() if r.requested_at else None,
                    'requested_by': r.requested_by.get_full_name() if r.requested_by else None,
                    'reason': r.reason,
                    'comments': r.comments,
                    'completed': bool(r.completed),
                    'test_data': r.test_data or {}
                })

        # current stage comments snapshot
        stage_comments = {
            'lab_qc_comments': getattr(report, 'lab_qc_comments', '') or '',
            'qao_comments': getattr(report, 'qao_comments', '') or '',
            'hod_test_comments': getattr(report, 'hod_test_comments', '') or '',
            'fm_test_comments': getattr(report, 'fm_test_comments', '') or '',
            'management_test_comments': getattr(report, 'management_test_comments', '') or '',
            'milan_comments': getattr(report, 'milan_comments', '') or ''
        }

        # approval logs (if any)
        logs = []
        approval_logs_qs = getattr(report, 'approval_logs', None)
        if approval_logs_qs is not None:
            for al in approval_logs_qs.all().order_by('-created_at'):
                logs.append({
                    'action': al.action,
                    'comments': al.comments,
                    'retest_reason': getattr(al, 'retest_reason', '') or '',
                    'status': getattr(al, 'status', '') or '',
                    'created_at': al.created_at.isoformat() if al.created_at else None,
                    'user': al.user.get_full_name() if al.user else None
                })

        payload = {
            'tests_to_be_done': tests_to_be_done,
            'tests_list': tests_list,
            'retests': retests,
            'stage_comments': stage_comments,
            'approval_logs': logs
        }

        return JsonResponse(payload)
    except RMTRRequest.DoesNotExist:
        return JsonResponse({'error': 'RMTR not found'}, status=404)

def get_rmtr_report(request, rmtr_no):
    try:
        rmtr = RMTRRequest.objects.get(rmtr_no=rmtr_no)
        data = {
            'rmtr_no': rmtr.rmtr_no,
            'material_type': rmtr.material_type,
            'sub_category': rmtr.sub_category,
            'status': rmtr.status,
            'date': rmtr.date.strftime('%Y-%m-%d'),
            'management_test_date_approved': rmtr.management_test_date_approved.strftime('%Y-%m-%d') if rmtr.management_test_date_approved else None,
        }
        return JsonResponse(data)
    except RMTRRequest.DoesNotExist:
        return JsonResponse({'error': 'RMTR not found'}, status=404)
        
def check_rmtr(request, rmtr_no):
    try:
        rmtrs = list(RMTRRequest.objects.filter(rmtr_no=rmtr_no).values())
        
        debug_info = {
            'requested_rmtr': rmtr_no,
            'found_rmtrs': rmtrs,
            'total_matching': len(rmtrs),
            'all_rmtrs': list(RMTRRequest.objects.values_list('rmtr_no', flat=True))
        }
        
        return JsonResponse(debug_info)
    except Exception as e:
        return JsonResponse({'error': str(e)})
    
# views.py

logger = logging.getLogger(__name__)
register = Library()

@register.filter
def multiply(value, arg):
    """Multiply the arg by the value"""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def add(value, arg):
    """Add the arg to the value"""
    try:
        return int(value) + int(arg)
    except (ValueError, TypeError):
        return 0

def get_base64_encoded_image(image_path):
    """Convert image to base64 string"""
    try:
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"Error encoding image {image_path}: {str(e)}")
        return None


@login_required
def download_rmtr_pdf(request, rmtr_no):
    """
    Generate and return PDF for RMTR report.
    Supports both preview (inline) and download (attachment) modes.
    """
    try:
        # Get the report with related data
        report = RMTRRequest.objects.select_related(
            'supplier',
            'plant'
        ).get(rmtr_no=rmtr_no)

        # Process test results
        test_results = []
        for i in range(1, 17):
            test = {
                'tests_carried_out': getattr(report, f'tests_carried_out{i}', ''),
                'sample_results': getattr(report, f'sample_results{i}', ''),
                'raw_material_results': getattr(report, f'raw_material_results{i}', ''),
                'kapa_standards': getattr(report, f'kapa_standards{i}', '')
            }
            # Only add tests that have actual content
            if any(value.strip() for value in test.values() if value):
                test_results.append(test)

        # Modified pagination logic - 6 items on first page, 7 on subsequent pages
        first_page_items = 6
        other_pages_items = 7
        total_items = len(test_results)
        
        # Calculate total pages needed
        remaining_items = max(0, total_items - first_page_items)
        additional_pages = (remaining_items + other_pages_items - 1) // other_pages_items if remaining_items > 0 else 0
        total_pages = 1 + additional_pages

        # Pre-process pages data
        pages_data = []
        
        # First page (up to 6 items)
        first_page_tests = test_results[:first_page_items]
        pages_data.append({
            'page_num': 0,
            'test_results': first_page_tests,
            'is_first_page': True,
            'is_last_page': total_pages == 1,
            'current_page': 1,
            'total_pages': total_pages
        })

        # Subsequent pages (up to 7 items each)
        if total_pages > 1:
            remaining_tests = test_results[first_page_items:]
            for page_num in range(1, total_pages):
                start_idx = (page_num - 1) * other_pages_items
                end_idx = min(start_idx + other_pages_items, len(remaining_tests))
                
                page_tests = remaining_tests[start_idx:end_idx]
                
                pages_data.append({
                    'page_num': page_num,
                    'test_results': page_tests,
                    'is_first_page': False,
                    'is_last_page': page_num == total_pages - 1,
                    'current_page': page_num + 1,
                    'total_pages': total_pages
                })

        # Use absolute paths for letterhead
        base_dir = Path(__file__).resolve().parent.parent
        static_dir = base_dir / 'static' / 'images'
        letterhead_path = static_dir / 'Letterhead.png'

        # Check if letterhead exists
        if not letterhead_path.exists():
            logger.error(f"Letterhead image not found at: {letterhead_path}")
            messages.error(request, 'Letterhead image not found')
            return redirect('completed_reports')

        # Encode letterhead image to base64
        try:
            with open(str(letterhead_path), 'rb') as img_file:
                letterhead_base64 = base64.b64encode(img_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to encode letterhead image: {str(e)}")
            messages.error(request, 'Error processing letterhead image')
            return redirect('completed_reports')

        # Prepare context for template
        context = {
            'report': report,
            'pages_data': pages_data,
            'generated_date': timezone.now(),
            'title': 'RAW MATERIAL TEST REPORT',
            'letterhead_base64': letterhead_base64,
            'total_pages': total_pages,
            'total_items': total_items
        }

        # Render the HTML template
        template = get_template('pdf/rmtr_report_pdf.html')
        html_content = template.render(context)

        # PDF generation options
        options = {
            'page-size': 'A4',
            'margin-top': '0',
            'margin-right': '0',
            'margin-bottom': '0',
            'margin-left': '0',
            'encoding': 'UTF-8',
            'enable-local-file-access': None,
            'quiet': None,
            'print-media-type': None,
            'zoom': 1.0,
            'dpi': 300,
            'orientation': 'Portrait',
            'background': True,
            'no-outline': None,
            'disable-smart-shrinking': True
        }

        # Configure wkhtmltopdf path
        wkhtmltopdf_path = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
        if not os.path.exists(wkhtmltopdf_path):
            # Try alternative paths
            alternative_paths = [
                '/usr/local/bin/wkhtmltopdf',
                '/usr/bin/wkhtmltopdf',
                'wkhtmltopdf'  # System PATH
            ]
            for alt_path in alternative_paths:
                if os.path.exists(alt_path):
                    wkhtmltopdf_path = alt_path
                    break
            else:
                logger.error(f"wkhtmltopdf not found")
                messages.error(request, 'PDF generation tool not found')
                return redirect('completed_reports')

        config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)

        # Generate PDF
        try:
            pdf = pdfkit.from_string(
                html_content, 
                False, 
                options=options, 
                configuration=config
            )
        except Exception as e:
            logger.error(f"PDF generation failed: {str(e)}")
            messages.error(request, 'Error generating PDF document')
            return redirect('completed_reports')

        # Create HTTP response with PDF content
        response = HttpResponse(pdf, content_type='application/pdf')
        
        # Set headers to allow iframe embedding
        response['X-Frame-Options'] = 'SAMEORIGIN'
        response['Content-Security-Policy'] = "frame-ancestors 'self';"
        
        # Determine if this is a preview or download request
        is_preview = request.GET.get('preview', '').lower() == 'true'
        
        # Set appropriate Content-Disposition header
        filename = f"RMTR_{report.rmtr_no}_{timezone.now().strftime('%Y%m%d')}.pdf"
        if is_preview:
            # inline disposition displays in browser/iframe
            response['Content-Disposition'] = f'inline; filename="{filename}"'
        else:
            # attachment disposition forces download
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Add cache control headers for better performance
        response['Cache-Control'] = 'private, max-age=3600'
        
        return response

    except RMTRRequest.DoesNotExist:
        logger.error(f"RMTR report not found: {rmtr_no}")
        messages.error(request, 'Report not found')
        return redirect('completed_reports')
    except Exception as e:
        logger.error(f"Unexpected error generating PDF: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        messages.error(request, 'Error generating PDF')
        return redirect('completed_reports')


    
@login_required
def preview_rmtr_pdf(request, rmtr_no):
    """Preview PDF in browser"""
    try:
        # Get the report with related data
        report = RMTRRequest.objects.select_related(
            'supplier',
            'plant'
        ).get(rmtr_no=rmtr_no)

        # Process test results
        test_results = []
        for i in range(1, 17):
            test = {
                'tests_carried_out': getattr(report, f'tests_carried_out{i}', ''),
                'sample_results': getattr(report, f'sample_results{i}', ''),
                'raw_material_results': getattr(report, f'raw_material_results{i}', ''),
                'kapa_standards': getattr(report, f'kapa_standards{i}', '')
            }
            # Only add tests that have actual content
            if any(value.strip() for value in test.values() if value):
                test_results.append(test)

        # Modified pagination logic
        first_page_items = 8
        other_pages_items = 7
        total_items = len(test_results)
        
        # Calculate total pages needed
        remaining_items = max(0, total_items - first_page_items)
        additional_pages = (remaining_items + other_pages_items - 1) // other_pages_items
        total_pages = 1 + additional_pages if remaining_items > 0 else 1

        # Pre-process pages data
        pages_data = []
        
        # First page
        first_page_tests = test_results[:first_page_items]
        pages_data.append({
            'page_num': 0,
            'test_results': first_page_tests,
            'is_first_page': True,
            'is_last_page': total_pages == 1,
            'current_page': 1,
            'total_pages': total_pages
        })

        # Subsequent pages
        remaining_tests = test_results[first_page_items:]
        for page_num in range(1, total_pages):
            start_idx = (page_num - 1) * other_pages_items
            end_idx = min(start_idx + other_pages_items, len(remaining_tests))
            
            page_tests = remaining_tests[start_idx:end_idx]
            
            pages_data.append({
                'page_num': page_num,
                'test_results': page_tests,
                'is_first_page': False,
                'is_last_page': page_num == total_pages - 1,
                'current_page': page_num + 1,
                'total_pages': total_pages
            })

        # Use absolute paths
        base_dir = Path(__file__).resolve().parent.parent
        static_dir = base_dir / 'static' / 'images'
        letterhead_path = static_dir / 'Letterhead.png'

        if not letterhead_path.exists():
            logger.error(f"Letterhead image not found at: {letterhead_path}")
            messages.error(request, 'Letterhead image not found')
            return redirect('completed_reports')

        try:
            letterhead_base64 = get_base64_encoded_image(letterhead_path)
            if not letterhead_base64:
                raise ValueError("Failed to encode letterhead image")
        except Exception as e:
            logger.error(f"Failed to encode letterhead image: {str(e)}")
            messages.error(request, 'Error processing letterhead image')
            return redirect('completed_reports')

        context = {
            'report': report,
            'pages_data': pages_data,
            'generated_date': timezone.now(),
            'title': 'RAW MATERIAL TEST REPORT',
            'letterhead_base64': letterhead_base64,
            'total_pages': total_pages,
            'total_items': total_items
        }

        template = get_template('pdf/rmtr_report_pdf.html')
        html_content = template.render(context)

        # PDF generation options
        options = {
            'page-size': 'A4',
            'margin-top': '0',
            'margin-right': '0',
            'margin-bottom': '0',
            'margin-left': '0',
            'encoding': 'UTF-8',
            'enable-local-file-access': None,
            'quiet': None,
            'print-media-type': None,
            'zoom': 1.0,
            'dpi': 300,
            'orientation': 'Portrait',
            'background': True,
            'no-outline': None,
            'disable-smart-shrinking': True
        }

        wkhtmltopdf_path = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
        if not os.path.exists(wkhtmltopdf_path):
            logger.error(f"wkhtmltopdf not found at: {wkhtmltopdf_path}")
            messages.error(request, 'PDF generation tool not found')
            return redirect('completed_reports')

        config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)

        try:
            pdf = pdfkit.from_string(
                html_content, 
                False, 
                options=options, 
                configuration=config
            )
        except Exception as e:
            logger.error(f"PDF generation failed: {str(e)}")
            messages.error(request, 'Error generating PDF document')
            return redirect('completed_reports')

        # Create response with proper headers for iframe embedding
        response = HttpResponse(content_type='application/pdf')
        response['X-Frame-Options'] = 'SAMEORIGIN'
        response['Content-Security-Policy'] = "frame-ancestors 'self';"
        response['Content-Disposition'] = f'inline; filename="RMTR_{report.rmtr_no}_{timezone.now().strftime("%Y%m%d")}.pdf"'
        response.write(pdf)
        
        return response

    except RMTRRequest.DoesNotExist:
        logger.error(f"RMTR report not found: {rmtr_no}")
        messages.error(request, 'Report not found')
        return redirect('completed_reports')
    except Exception as e:
        logger.error(f"Error previewing PDF for RMTR {rmtr_no}: {str(e)}")
        messages.error(request, 'Error generating PDF preview')
        return redirect('completed_reports')

    
    
@login_required
def get_rmtr_tests_duplicate(request, rmtr_no):
    try:
        report = RMTRRequest.objects.get(rmtr_no=rmtr_no)

        tests_to_be_done = getattr(report, 'tests', '') or ''
        tests_list = RMTRTestView.get_test_data(report)

        retests = []
        if hasattr(report, 'rmtr_retests'):
            for r in report.rmtr_retests.all().order_by('-requested_at'):
                retests.append({
                    'requested_at': r.requested_at.isoformat() if r.requested_at else None,
                    'requested_by': r.requested_by.get_full_name() if r.requested_by else None,
                    'reason': r.reason,
                    'comments': r.comments,
                    'completed': bool(r.completed),
                    'test_data': r.test_data or {}
                })

        stage_comments = {
            'lab_qc_comments': getattr(report, 'lab_qc_comments', '') or '',
            'qao_comments': getattr(report, 'qao_comments', '') or '',
            'hod_test_comments': getattr(report, 'hod_test_comments', '') or '',
            'fm_test_comments': getattr(report, 'fm_test_comments', '') or '',
            'management_test_comments': getattr(report, 'management_test_comments', '') or '',
            'milan_comments': getattr(report, 'milan_comments', '') or ''
        }

        logs = []
        if hasattr(report, 'approval_logs'):
            for al in report.approval_logs.all().order_by('-created_at'):
                logs.append({
                    'action': al.action,
                    'comments': al.comments,
                    'retest_reason': getattr(al, 'retest_reason', '') or '',
                    'status': getattr(al, 'status', '') or '',
                    'created_at': al.created_at.isoformat() if al.created_at else None,
                    'user': al.user.get_full_name() if al.user else None
                })

        payload = {
            'tests_to_be_done': tests_to_be_done,
            'tests_list': tests_list,
            'retests': retests,
            'stage_comments': stage_comments,
            'approval_logs': logs
        }

        return JsonResponse(payload)
    except RMTRRequest.DoesNotExist:
        return JsonResponse({'error': 'Report not found'}, status=404)

    
    
    
    
    
    
    
    
    
    
    
    
#IMPORTS SECTION

@api_view(['POST'])
def create_imp_rmtr_request(request):
    if request.method == 'POST':
        form = IMP_RMTRRequestForm(request.POST, request.FILES)
        if form.is_valid():
            imp_rmtr_request = form.save(commit=False)
            imp_rmtr_request.imp_rmtr_no = generate_imp_rmtr_number()
            imp_rmtr_request.save()
            return JsonResponse({
                'status': 'success',
                'redirect': '/dashboard/',  # Redirect to the dashboard on success
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': form.errors.as_json(),
            }, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

logger = logging.getLogger(__name__)

IMP_STATUS_DISPLAY_MAPPING = {
    'pending: hod purchase approval': 'report_created',
    'pending hod purchase approval': 'report_created',
    'pending:hod purchase approval': 'report_created',
    'pending : hod purchase approval': 'report_created',
    'Pending: HOD Purchase approval': 'report_created',
    'Pending: HOD Purchase Approval': 'report_created',
    'PENDING: HOD PURCHASE APPROVAL': 'report_created',
    
    #'pending: management approval': 'hod_purchase_approved',
    #'pending: management 2nd approval': 'management_approved',
    #'pending: fm approval': 'management_approved_2',
    #'pending: hod approval': 'fm_approved',
    
    #'pending: hod approval': 'management_approved_2',
    'pending: hod approval': 'hod_purchase_approved',
    
    'pending: lab test': 'hod_approved',
    'pending: qao test approval': 'test_completed',
    'pending: hod test approval': 'qao_test_approval',
    
    #'pending: fm test approval': 'hod_test_approved',
    #'pending: management test approval': 'fm_test_approved',
    
    'pending: management test approval':'hod_test_approved',
    #'pending: management test approval':'qao_test_approved',
    #'pending: milan approval': 'management_test_approved',
    #'completed': 'milan_approved'
    'completed': 'management_test_approved',
}

# Status display mapping
IMP_STATUS_DISPLAY_MAPPING = {
    'report_created': 'Pending: HOD Purchase Approval',
    'hod_purchase_approved':'Pending: HOD Approval',
    
    #'hod_purchase_approved': 'Pending: Management Approval',
    #'management_approved': 'Pending: Management 2nd Approval',
    #'management_approved_2': 'Pending: FM Approval',
    #'fm_approved': 'Pending: HOD Approval',
    
    #'management_approved_2':'Pending: HOD Approval',
    
    'hod_approved': 'Pending: Lab Test',
    'test_completed': 'Pending: QAO Review',
    #'qao_reviewed':'Pending: Management Test Approval',
    'qao_reviewed': 'Pending: HOD Test Approval',
    
    #'hod_test_approved': 'Pending: FM Test Approval',
    #'fm_test_approved': 'Pending: Management Test Approval',
    
    'hod_test_approved':'Pending: Management Test Approval',
    'management_test_approved': 'completed',
    #'management_test_approved': 'Pending: milan approval',
    #'milan_approved': 'completed',
    
    'rejected': 'Rejected',
    'pending_retest': 'Pending: Retest',
    'retesting': 'Retesting in Progress',
    'retest_completed': 'Retest Completed: Pending Review'
}


# Status configuration
IMP_STATUS_CONFIG = {
    'report_created': {
        'display': 'Pending: HOD Purchase Approval',
        'next_stage': 'hod_purchase_approved',
        'group': 'HOD_PURCHASE, PURCHASE',
        'can_retest': False
    },
    
    'hod_purchase_approved': {
        'display': 'Pending: HOD Approval',
        'next_stage': 'hod_approved',
        'group': 'HOD_PURCHASE',
        'can_retest': False
    },
    
    
     """
    'hod_purchase_approved': {
        'display': 'Pending: Management Approval',
        'next_stage': 'management_approved',
        'group': 'HOD_PURCHASE',
        'can_retest': False
    },
    'management_approved': {
        'display': 'Pending: Management 2nd Approval',
        'next_stage': 'management_approved_2',
        'group': 'MANAGEMENT',
        'can_retest': False
    },
   
    'management_approved_2': {
        'display': 'Pending: FM Approval',
        'next_stage': 'MANAGEMENT_2',
        'group': 'MANAGEMENT_2',
        'can_retest': False
    },
    'fm_approved': {
        'display': 'Pending: HOD Approval',
        'next_stage': 'hod_approved',
        'group': 'FM',
        'can_retest': False
    },
    
    
    'management_approved_2': {
        'display': 'Pending: HOD Approval',
        'next_stage': 'MANAGEMENT_2',
        'group': 'MANAGEMENT_2',
        'can_retest': False
    },
    """
    
    
    'hod_approved': {
        'display': 'Pending: Lab Test',
        'next_stage': 'test_completed',
        'group': 'HOD',
        'can_retest': False
    },
    'test_completed': {
        'display': 'Pending: QAO Review',
        'next_stage': 'qao_reviewed',
        'group': 'QC',
        'can_retest': True,
        'retest_chain': ['QAO', 'QC']
    },
    
    'qao_reviewed': {
        'display': 'Pending: HOD Test Approval',
        'next_stage': 'hod_test_approved',
        'group': 'QAO',
        'can_retest': True,
        'retest_chain': ['HOD_TEST', 'QAO', 'QC']
    },
    """
    'qao_reviewed': {
        'display': 'Pending: HOD Test Approval',
        'next_stage': 'hod_test_approved',
        'group': 'QAO',
        'can_retest': True,
        'retest_chain': ['HOD_TEST', 'QAO', 'QC']
    },
    # 'hod_test_approved': {
    #     'display': 'Pending: FM Test Approval',
    #     'next_stage': 'fm_test_approved',
    #     'group': 'HOD_TEST',
    #     'can_retest': True,
    #     'retest_chain': ['FM_TEST', 'HOD_TEST', 'QAO', 'QC']
    # },
        'hod_test_approved': {
        'display': 'Pending: Management Test Approval',
        'next_stage': 'management_test_approved',
        'group': 'HOD_TEST',
        'can_retest': True,
        'retest_chain': ['FM_TEST', 'HOD_TEST', 'QAO', 'QC']
    },
        
    
    'fm_test_approved': {
        'display': 'Pending: Management Test Approval',
        'next_stage': 'management_test_approved',
        'group': 'FM_TEST',
        'can_retest': True,
        'retest_chain': ['FM_TEST', 'HOD_TEST', 'QAO', 'QC']
    },
    
    
    'management_test_approved': {
        'display': 'Pending: Milan Approval',
        'next_stage': 'milan_approved',
        'group': 'MANAGEMENT_TEST',
        'can_retest': True,
        'retest_chain': ['MANAGEMENT_TEST', 'FM_TEST', 'HOD_TEST', 'QAO', 'QC']
    },
    
    'milan_approved': {
        'display': 'completed',
        'next_stage': None,
        'group': 'MILAN',
        'can_retest': False,
        
    },
    """
    'hod_test_approved': {
        'display': 'Pending: Management Test Approval',
        'next_stage': 'management_test_approved',
        'group': 'HOD_TEST',
        'can_retest': True,
        'retest_chain': ['FM_TEST', 'HOD_TEST', 'QAO', 'QC']
    },
    
    'management_test_approved': {
        'display': 'completed',
        'next_stage': None,
        'group': 'MANAGEMENT_TEST',
        'can_retest': True,
        'retest_chain': ['MANAGEMENT_TEST', 'FM_TEST', 'HOD_TEST', 'QAO', 'QC']
    },
    
    
    
    'pending_retest': {
        'display': 'Pending: Retest',
        'next_stage': 'retesting',
        'group': 'LAB',
        'can_retest': False
    },
    'retesting': {
        'display': 'Retesting in Progress',
        'next_stage': 'retest_completed',
        'group': 'LAB',
        'can_retest': False
    },
    'retest_completed': {
        'display': 'Retest Completed: Pending Review',
        'next_stage': None,
        'group': None,
        'can_retest': False
    }
}

# Group to status mapping
IMP_GROUP_STATUS_MAPPING = {
   'HOD_PURCHASE': ['report_created'],
    'MANAGEMENT': ['hod_purchase_approved', 'management_approved'],
    'FM': ['management_approved_2'],
    'HOD': ['fm_approved'],
    'LAB': ['hod_approved', 'pending_retest', 'retesting'],
    'QAO': ['test_completed', 'pending_retest', 'retesting', 'retest_completed'],
    'HOD_TEST': ['qao_reviewed', 'pending_retest', 'retesting', 'retest_completed'],
    #'FM_TEST': ['hod_test_approved', 'pending_retest', 'retesting', 'retest_completed'],
    'MANAGEMENT_TEST': ['fm_test_approved', 'pending_retest', 'retesting', 'retest_completed'],
    'MILAN': ['management_test_approved', 'milan_approval'],
    'ADMIN': ['report_created', 'hod_purchase_approved', 'management_approved', 'management_approved_2',
              'fm_approved', 'hod_approved', 'test_completed', 'qao_reviewed', 'hod_test_approved',
              'fm_test_approved', 'management_test_approved', 'milan_approval', 'completed', 'rejected',
              'pending_retest', 'retesting', 'retest_completed']
}
def normalize_imp_status(status):
    """Normalize status string to internal format for IMP RMTR"""
    if not status:
        return ''
    
    status = str(status).lower().strip()
    
    # Direct status mapping
    status_mapping = {
        'pending: hod purchase approval': 'report_created',
        'pending hod purchase approval': 'report_created',
        'pending:hod purchase approval': 'report_created',
        'pending : hod purchase approval': 'report_created',
        'pending: hod approval': 'hod_purchase_approved',
        
        #'pending: management approval': 'hod_purchase_approved',
        #'pending: management 2nd approval': 'management_approved',
        #'pending: fm approval': 'management_approved_2',
        #'pending: hod approval': 'fm_approved',
        
        #'pending: hod approval':'management_approved_2',
        
        'pending: lab test': 'hod_approved',
        'pending: qao review': 'test_completed',
        #'pending: hod test approval': 'qao_reviewed',
        #'pending: fm test approval': 'hod_test_approved',
        #'pending: management test approval': 'fm_test_approved',
        # 'hod_test_approved',
        
        'pending: hod test approval':'qao_reviewed',
        'pending: management test approval':'hod_test_approved',
        'completed': 'management_test_approved',
        #'pending: milan approval': 'management_test_approved',
        #'completed': 'milan_approved'
    }
    
    # Try exact match first
    normalized = status_mapping.get(status)
    if normalized:
        return normalized
        
    # Try matching without punctuation
    clean_status = re.sub(r'[:\s]+', ' ', status).strip()
    if clean_status in status_mapping:
        return status_mapping[clean_status]
    
    # Handle retest cases
    if 'retest' in status:
        if any(x in status for x in ['pending retest', 'pending:retest', 'pending: retest']):
            return 'pending_retest'
        if 'retesting' in status:
            return 'retesting'
        if 'retest completed' in status:
            return 'retest_completed'
            
    # If no match found, return original status
    return status

# Status display mapping for IMP requests
IMP_STATUS_DISPLAY_MAPPING = {
    'pending: hod purchase approval': 'report_created',
    'pending hod purchase approval': 'report_created',
    'pending:hod purchase approval': 'report_created',
    'pending : hod purchase approval': 'report_created',
    'Pending: HOD Purchase approval': 'report_created',
    'Pending: HOD Purchase Approval': 'report_created',
    'PENDING: HOD PURCHASE APPROVAL': 'report_created',
    
    #'pending: management approval': 'hod_purchase_approved',
    #'pending: management 2nd approval': 'management_approved',
    #'pending: fm approval': 'management_approved_2',
    #'pending: hod approval': 'fm_approved',
    #'pending: hod approval': 'management_approved_2',
    'pending: hod approval':'hod_purchase_approved',
    'pending: lab test': 'hod_approved',
    'pending: qao test approval': 'test_completed',
    
    
    #'pending: hod test approval': 'qao_test_approval',
    #'pending: fm test approval': 'hod_test_approved',
    #'pending: management test approval': 'fm_test_approved',
    #'pending: management test approval':'hod_test_approved',
    'pending: hod test approval': 'qao_test_approval',
    'pending: management test approval':'hod_test_approval',
    'completed':'management_test_approved'
    #'pending: milan approval': 'management_test_approved',
    #'completed': 'milan_approved'
}

@login_required
def imp_pending(request):
    try:
        user_groups = list(request.user.groups.values_list('name', flat=True))
        logger.info(f"User groups for {request.user.username}: {user_groups}")

        if not user_groups:
            messages.error(request, 'You do not have any assigned roles. Please contact your administrator.')
            return redirect('login')

        # Define statuses to exclude
        excluded_statuses = ['completed', 'rejected', 'milan_approved']

        # Get IMP requests excluding completed and rejected
        reports = IMP_RMTRRequest.objects.exclude(
            status__in=excluded_statuses
        ).exclude(
            status__icontains='completed'
        ).exclude(
            status__icontains='rejected'
        )

        # Apply search if provided
        search_query = request.GET.get('search')
        if search_query:
            reports = reports.filter(
                Q(imp_rmtr_no__icontains=search_query) |
                Q(supplier__name__icontains=search_query) |
                Q(material_type__icontains=search_query) |
                Q(plant__name__icontains=search_query)
            )

        # Apply sorting
        sort_field = request.GET.get('sort', '-date_created')
        if sort_field == 'date_created':
            sort_field = '-date_created'
        elif sort_field == 'imp_rmtr_no':
            sort_field = '-imp_rmtr_no'

        reports = reports.order_by(sort_field)

        # Process each report for display
        for report in reports:
            normalized_status = normalize_status(report.status)
            report.internal_status = normalized_status
            
            # Set display status using the mapping
            config = STATUS_CONFIG.get(normalized_status, {})
            report.display_status = config.get('display', report.status)
            
            # Add retest capabilities
            report.can_retest = config.get('can_retest', False)
            if report.can_retest:
                report.retest_chain = config.get('retest_chain', [])
                report.user_can_retest = any(group in report.retest_chain for group in user_groups)
            else:
                report.user_can_retest = False

        # Render all rows so client-side search covers every report
        reports = list(reports)

        context = {
            'pending_reports': reports,
            'user_groups': user_groups,
            'search_query': search_query,
            'current_sort': sort_field,
            'status_config': STATUS_CONFIG,
            'status_display_mapping': STATUS_DISPLAY_MAPPING
        }

        return render(request, 'imp_all_rmtrs.html', context)

    except Exception as e:
        logger.exception(f"Error in imp_pending_view: {str(e)}")
        messages.error(request, 'An error occurred while loading the dashboard.')
        return redirect('dashboard')


# Maximum image size (10MB)
MAX_IMAGE_SIZE = 10 * 1024 * 1024

# Valid image types
VALID_IMAGE_TYPES = [
    'image/jpeg', 
    'image/png', 
    'image/gif',
    'image/bmp',
    'image/webp',
    'image/tiff',
    'image/svg+xml',
    'image/x-icon',
    'image/heic',
    'image/heif'
]


"""
@login_required
def imp_test_request(request, imp_rmtr_no=None):
    #Handle both new IMP RMTR requests and updates
    allowed_groups = ['PURCHASE', 'ADMIN', 'HOD_PURCHASE']
    if not request.user.groups.filter(name__in=allowed_groups).exists():
        return JsonResponse({
            'status': 'error',
            'message': 'Permission denied. You do not have access to this page.'
        }, status=403)
    
    try:
        if request.method == 'POST':
            try:
                # Create new report
                report = IMP_RMTRRequest()
                
                # Set the user fields
                report.created_by = request.user
                report.current_user = request.user  

                # Generate new IMP RMTR number
                current_year = timezone.now().year
                try:
                    last_entry = IMP_RMTRRequest.objects.filter(
                        imp_rmtr_no__iregex=f'^IMP-{current_year}-[0-9]{{4}}$'
                    ).order_by('-imp_rmtr_no').first()
                    
                    if last_entry:
                        prefix, year_part, number_part = last_entry.imp_rmtr_no.split('-')
                        new_number = int(number_part) + 1
                    else:
                        new_number = 1
                    
                    new_imp_rmtr_no = f'IMP-{current_year}-{str(new_number).zfill(4)}'
                    
                    # Check if the generated number already exists
                    if IMP_RMTRRequest.objects.filter(imp_rmtr_no=new_imp_rmtr_no).exists():
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Generated IMP RMTR number already exists. Please try again.'
                        }, status=400)
                    
                    report.imp_rmtr_no = new_imp_rmtr_no
                    
                except Exception as e:
                    logger.error(f"Error generating IMP RMTR number: {str(e)}")
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Error generating IMP RMTR number'
                    }, status=500)

                # Set fields from form data
                report.date = request.POST.get('date') or timezone.now().date()
                
                # Fetch and validate the supplier instance
                supplier_id = request.POST.get('supplier')
                if supplier_id:
                    try:
                        report.supplier = get_object_or_404(Supplier, id=supplier_id)
                    except Exception as e:
                        return JsonResponse({
                            'status': 'error',
                            'message': f'Invalid supplier ID: {supplier_id}'
                        }, status=400)
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Supplier is required'
                    }, status=400)
                
                # Fetch and validate the plant instance
                plant_id = request.POST.get('plant')
                if plant_id:
                    try:
                        report.plant = get_object_or_404(Plant, id=plant_id)
                    except Exception as e:
                        return JsonResponse({
                            'status': 'error',
                            'message': f'Invalid plant ID: {plant_id}'
                        }, status=400)
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Plant is required'
                    }, status=400)

                # Handle approvers with validation
            

            '''
                approvers = request.POST.get('approved-mgt', '').strip()
                if not approvers:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'At least one approver is required'
                    }, status=400)
                
                if ',' in approvers:
                    first_approver, second_approver = approvers.split(',')
                    report.approved_mgt = first_approver.strip()
                    report.second_approver = second_approver.strip()
                    logger.info(f"Set approvers for IMP RMTR {report.imp_rmtr_no}: First={first_approver.title()}, Second={second_approver.title()}")
                else:
                    report.approved_mgt = approvers
                    report.second_approver = None
                    logger.info(f"Set single approver for IMP RMTR {report.imp_rmtr_no}: {approvers}")
                '''

                # Other fields with validation
                report.material_name = request.POST.get('material_name')
                report.material_type = request.POST.get('material_type', '')
                report.sub_category = request.POST.get('sub_category', '')
                report.tests = request.POST.get('selected_tests', '')
                report.requested_by = request.POST.get('requested-by') or request.user.get_full_name()
                report.justification = request.POST.get('justification', '')
                report.uom = request.POST.get('uom', '')
                report.specs = request.POST.get('specs', '')
                report.status = 'Pending: HOD Purchase approval'
                report.created_at = timezone.now()
                
                # Validate quantity
                quantity = request.POST.get('quantity', '')
                if quantity:
                    try:
                        report.quantity = float(quantity)
                    except ValueError:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Quantity must be a valid number'
                        }, status=400)
                
                # Handle and validate image upload
                if 'image-upload' in request.FILES:
                    image = request.FILES['image-upload']
                    
                    # Validate image size (10MB)
                    if image.size > 10 * 1024 * 1024:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Image size should be less than 10MB'
                        }, status=400)
                    
                    # Validate image type
                    valid_types = ['image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/webp', 
                                 'image/tiff', 'image/svg+xml', 'image/x-icon', 'image/heic', 'image/heif']
                    if hasattr(image, 'content_type') and image.content_type not in valid_types:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Invalid image type. Allowed formats are JPEG, PNG, GIF, BMP, WebP, TIFF, SVG, ICO, HEIC, and HEIF.'
                        }, status=400)
                    
                    report.image = image
                
                # Validate required fields
                required_fields = {
                    'created_by': report.created_by,
                    'current_user': report.current_user,
                    'supplier': report.supplier,
                    'material_name': report.material_name,
                    'plant': report.plant,
                    'material_type': report.material_type,
                    'tests': report.tests,
                    #'approved_mgt': report.approved_mgt,
                    'quantity': report.quantity,
                    'uom': report.uom
                }
                
                missing_fields = [field for field, value in required_fields.items() if not value]
                if missing_fields:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Missing required fields: {", ".join(missing_fields)}'
                    }, status=400)
                
                # Save the report with transaction
                with transaction.atomic():
                    report.save()
                    logger.info(f"Successfully created new IMP report: {report.imp_rmtr_no} by user {request.user}")
                    
                    # Prepare email notification
                    subject = f'New Imports RMTR Request Created - {report.imp_rmtr_no}'
                    supplier_name = report.supplier.name if report.supplier else "N/A"
                    plant_name = report.plant.name if report.plant else "N/A"
            
                    message = f'''
                    A new Imports RMTR request has been created with the following details:
                    
                    RMTR Number: {report.imp_rmtr_no}
                    Date: {report.date}
                    Material: {report.material_name}
                    Supplier: {supplier_name}
                    Plant: {plant_name}
                    Material Type: {report.material_type}
                    Sub Category: {report.sub_category}
                    
                    Tests Required: {report.tests}


                    Justification: {report.justification}
                    Quantity: {report.quantity} {report.uom}
                    Specifications: {report.specs}

                    Created By: {report.created_by.get_full_name() or report.created_by.username}
                                        
                    Raw Material Test Report Link: http://10.0.0.7:8020
                    '''
                    
                    # Set up recipients list
                    recipients = [
                        'peter.busolo@kapa-oil.com',
                        'imports.user3@kapa-oil.com',
                        'purchase.user1@kapa-oil.com',
                        'ict@kapa-oil.com',
                        request.user.email
                    ]
                    
                    # Removak of any empty values
                    recipients = [email for email in recipients if email]
                    
                    if not recipients:
                        logger.warning(f"No valid email recipients for IMP RMTR {report.imp_rmtr_no}")
                    else:
                        try:
                            send_mail(
                                subject=subject,
                                message=message,
                                from_email='kapaportal@kapa-oil.local',
                                recipient_list=recipients,
                                fail_silently=True,
                            )
                            logger.info(f"Notification email sent for IMP RMTR {report.imp_rmtr_no} to {', '.join(recipients)}")
                        except Exception as e:
                            logger.error(f"Error sending email for IMP RMTR {report.imp_rmtr_no}: {str(e)}")
                    
                    return JsonResponse({
                        'status': 'success',
                        'message': 'IMP test request created successfully',
                        'redirect': '/dashboard/',
                        'imp_rmtr_no': report.imp_rmtr_no
                    })
                
            except Exception as e:
                logger.error(f"Error creating new IMP report: {str(e)}")
                logger.error(traceback.format_exc())
                return JsonResponse({
                    'status': 'error',
                    'message': str(e)
                }, status=500)
        
        else:  # GET request
            current_year = timezone.now().year
            try:
                last_entry = IMP_RMTRRequest.objects.filter(
                    imp_rmtr_no__iregex=f'^IMP-{current_year}-[0-9]{{4}}$'
                ).order_by('-imp_rmtr_no').first()
                
                if last_entry:
                    prefix, year_part, number_part = last_entry.imp_rmtr_no.split('-')
                    new_number = int(number_part) + 1
                else:
                    new_number = 1
                
                next_imp_rmtr_no = f'IMP-{current_year}-{str(new_number).zfill(4)}'
                
                # Validate that the generated number doesn't already exist
                if IMP_RMTRRequest.objects.filter(imp_rmtr_no=next_imp_rmtr_no).exists():
                    logger.error(f"Generated IMP RMTR number {next_imp_rmtr_no} already exists")
                    next_imp_rmtr_no = f'IMP-{current_year}-0001'
                    
            except Exception as e:
                logger.error(f"Error generating initial IMP RMTR number: {str(e)}")
                next_imp_rmtr_no = f'IMP-{current_year}-0001'

            context = {
                'imp_rmtr_no': next_imp_rmtr_no,
                'suppliers': Supplier.objects.all().order_by('name'),
                'plants': Plant.objects.all().order_by('name')
            }
            
            return render(request, 'imp_test_request.html', context)
        
    except Exception as e:
        logger.error(f"Error in imp_test_request view: {str(e)}")
        logger.error(traceback.format_exc())
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

"""



MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

# Valid file types dictionary
VALID_FILE_TYPES = {
    'image': [
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/bmp',
        'image/webp',
        'image/tiff',
        'image/svg+xml',
        'image/x-icon',
        'image/heic',
        'image/heif'
    ],
    'pdf': [
        'application/pdf',
        'application/x-pdf',
        'application/acrobat',
        'application/vnd.pdf',
        'text/pdf',
        'text/x-pdf'
    ]
}
@login_required
def imp_test_request(request, imp_rmtr_no=None):
    """Handle both new IMP RMTR requests and updates"""
    allowed_groups = ['PURCHASE', 'ADMIN', 'HOD_PURCHASE']
    if not request.user.groups.filter(name__in=allowed_groups).exists():
        return JsonResponse({
            'status': 'error',
            'message': 'Permission denied. You do not have access to this page.'
        }, status=403)
    
    try:
        if request.method == 'POST':
            try:
                # Create new report
                report = IMP_RMTRRequest()
                
                # Set the user fields
                report.created_by = request.user
                report.current_user = request.user

                # Generate new IMP RMTR number
                current_year = timezone.now().year
                try:
                    last_entry = IMP_RMTRRequest.objects.filter(
                        imp_rmtr_no__iregex=f'^IMP-{current_year}-[0-9]{{4}}$'
                    ).order_by('-imp_rmtr_no').first()
                    
                    if last_entry:
                        prefix, year_part, number_part = last_entry.imp_rmtr_no.split('-')
                        new_number = int(number_part) + 1
                    else:
                        new_number = 1
                    
                    new_imp_rmtr_no = f'IMP-{current_year}-{str(new_number).zfill(4)}'
                    
                    # Check if the generated number already exists
                    if IMP_RMTRRequest.objects.filter(imp_rmtr_no=new_imp_rmtr_no).exists():
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Generated IMP RMTR number already exists. Please try again.'
                        }, status=400)
                    
                    report.imp_rmtr_no = new_imp_rmtr_no
                    
                except Exception as e:
                    logger.error(f"Error generating IMP RMTR number: {str(e)}")
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Error generating IMP RMTR number'
                    }, status=500)

                # Set fields from form data
                report.date = request.POST.get('date') or timezone.now().date()
                
                # Fetch and validate the supplier instance
                supplier_id = request.POST.get('supplier')
                if supplier_id:
                    try:
                        report.supplier = get_object_or_404(Supplier, id=supplier_id)
                    except Exception as e:
                        return JsonResponse({
                            'status': 'error',
                            'message': f'Invalid supplier ID: {supplier_id}'
                        }, status=400)
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Supplier is required'
                    }, status=400)
                
                # Fetch and validate the plant instance
                plant_id = request.POST.get('plant')
                if plant_id:
                    try:
                        report.plant = get_object_or_404(Plant, id=plant_id)
                    except Exception as e:
                        return JsonResponse({
                            'status': 'error',
                            'message': f'Invalid plant ID: {plant_id}'
                        }, status=400)
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Plant is required'
                    }, status=400)

                # Other fields with validation
                report.material_name = request.POST.get('material_name')
                report.material_type = request.POST.get('material_type', '')
                report.sub_category = request.POST.get('sub_category', '')
                report.tests = request.POST.get('selected_tests', '')
                report.requested_by = request.POST.get('requested-by') or request.user.get_full_name()
                report.justification = request.POST.get('justification', '')
                report.uom = request.POST.get('uom', '')
                report.specs = request.POST.get('specs', '')
                report.status = 'Pending: HOD Purchase approval'
                report.created_at = timezone.now()
                
                # Validate quantity
                quantity = request.POST.get('quantity', '')
                if quantity:
                    try:
                        report.quantity = float(quantity)
                    except ValueError:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Quantity must be a valid number'
                        }, status=400)
                
                # Validate required fields
                required_fields = {
                    'created_by': report.created_by,
                    'current_user': report.current_user,
                    'supplier': report.supplier,
                    'material_name': report.material_name,
                    'plant': report.plant,
                    'material_type': report.material_type,
                    'tests': report.tests,
                    'quantity': report.quantity,
                    'uom': report.uom
                }
                
                missing_fields = [field for field, value in required_fields.items() if not value]
                if missing_fields:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Missing required fields: {", ".join(missing_fields)}'
                    }, status=400)

                # Save the report with transaction to handle file uploads
                with transaction.atomic():
                    # First save the report to get the imp_rmtr_no
                    report.save()
                    logger.info(f"Created new IMP report: {report.imp_rmtr_no}")

                    # Handle image uploads
                    images = request.FILES.getlist('image-upload[]')
                    image_names = []
                    for image in images:
                        if image.size > MAX_FILE_SIZE:
                            raise ValidationError(f'Image {image.name} exceeds 10MB limit')

                        if image.content_type not in VALID_FILE_TYPES['image']:
                            raise ValidationError(f'Invalid image type for {image.name}')

                        attachment = DocumentAttachment(
                            report=report,
                            file=image,
                            file_type='image'
                        )
                        attachment.save()
                        image_names.append(image.name)
                        logger.info(f"Saved image {image.name} for IMP RMTR {report.imp_rmtr_no}")

                    # Handle PDF uploads
                    pdfs = request.FILES.getlist('pdf-upload[]')
                    pdf_names = []
                    for pdf in pdfs:
                        if pdf.size > MAX_FILE_SIZE:
                            raise ValidationError(f'PDF {pdf.name} exceeds 10MB limit')

                        if pdf.content_type not in VALID_FILE_TYPES['pdf']:
                            raise ValidationError(f'Invalid file type for {pdf.name}')

                        attachment = DocumentAttachment(
                            report=report,
                            file=pdf,
                            file_type='pdf'
                        )
                        attachment.save()
                        pdf_names.append(pdf.name)
                        logger.info(f"Saved PDF {pdf.name} for IMP RMTR {report.imp_rmtr_no}")

                    # Prepare email notification
                    subject = f'New Imports RMTR Request Created - {report.imp_rmtr_no}'
                    supplier_name = report.supplier.name if report.supplier else "N/A"
                    plant_name = report.plant.name if report.plant else "N/A"
                    
                    # Include file information in email
                    attachments_info = ""
                    if image_names:
                        attachments_info += f"\nImages ({len(image_names)}):\n" + "\n".join(f"- {name}" for name in image_names)
                    if pdf_names:
                        attachments_info += f"\n\nPDFs ({len(pdf_names)}):\n" + "\n".join(f"- {name}" for name in pdf_names)
                    
                    message = f"""
                    A new Imports RMTR request has been created with the following details:
                    
                    RMTR Number: {report.imp_rmtr_no}

                    Date: {report.date_created}

                    Material Name: {report.material_name}

                    Supplier: {supplier_name}

                    Plant: {plant_name}

                    Material Type: {report.material_type}

                    Sub Category: {report.sub_category}
                    
                    Tests Required: {report.tests}
                    
                    
                    Justification: {report.justification}

                    Quantity: {report.quantity} {report.uom}

                    Specifications: {report.specs}
                    
                    Created By: {report.created_by.get_full_name() or report.created_by.username}
                    
                    Attachments: {attachments_info}
                    
                    Raw Material Test Report Link: http://10.0.0.7:8020
                    """
                    
                    # Set up recipients list
                    recipients = [
                        'peter.busolo@kapa-oil.com',
                        'imports.user3@kapa-oil.com',
                        'ict@kapa-oil.com',
                        request.user.email
                    ]
                    
                    # Remove any empty values
                    recipients = [email for email in recipients if email]
                    
                    if not recipients:
                        logger.warning(f"No valid email recipients for IMP RMTR {report.imp_rmtr_no}")
                    else:
                        try:
                            send_mail(
                                subject=subject,
                                message=message,
                                from_email='kapaportal@kapa-oil.local',
                                recipient_list=recipients,
                                fail_silently=True,
                            )
                            logger.info(f"Notification email sent for IMP RMTR {report.imp_rmtr_no} to {', '.join(recipients)}")
                        except Exception as e:
                            logger.error(f"Error sending email for IMP RMTR {report.imp_rmtr_no}: {str(e)}")
                    
                    return JsonResponse({
                        'status': 'success',
                        'message': 'IMP test request created successfully',
                        'redirect': '/dashboard/',
                        'imp_rmtr_no': report.imp_rmtr_no
                    })
                
            except ValidationError as e:
                return JsonResponse({
                    'status': 'error',
                    'message': str(e)
                }, status=400)
            except Exception as e:
                logger.error(f"Error creating new IMP report: {str(e)}")
                logger.error(traceback.format_exc())
                return JsonResponse({
                    'status': 'error',
                    'message': str(e)
                }, status=500)
        
        else:  # GET request
            current_year = timezone.now().year
            try:
                last_entry = IMP_RMTRRequest.objects.filter(
                    imp_rmtr_no__iregex=f'^IMP-{current_year}-[0-9]{{4}}$'
                ).order_by('-imp_rmtr_no').first()
                
                if last_entry:
                    prefix, year_part, number_part = last_entry.imp_rmtr_no.split('-')
                    new_number = int(number_part) + 1
                else:
                    new_number = 1
                
                next_imp_rmtr_no = f'IMP-{current_year}-{str(new_number).zfill(4)}'
                
                # Validate that the generated number doesn't already exist
                if IMP_RMTRRequest.objects.filter(imp_rmtr_no=next_imp_rmtr_no).exists():
                    logger.error(f"Generated IMP RMTR number {next_imp_rmtr_no} already exists")
                    next_imp_rmtr_no = f'IMP-{current_year}-0001'
                    
            except Exception as e:
                logger.error(f"Error generating initial IMP RMTR number: {str(e)}")
                next_imp_rmtr_no = f'IMP-{current_year}-0001'

            context = {
                'imp_rmtr_no': next_imp_rmtr_no,
                'suppliers': Supplier.objects.all().order_by('name'),
                'plants': Plant.objects.all().order_by('name')
            }
            
            return render(request, 'imp_test_request.html', context)
        
    except Exception as e:
        logger.error(f"Error in imp_test_request view: {str(e)}")
        logger.error(traceback.format_exc())
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)




        
@require_http_methods(["GET"])
@api_view(['GET'])
def generate_imp_rmtr_number(request):

     
    try:
        current_year = timezone.now().year
        
        with transaction.atomic():  # Prevent race conditions
            # Use select_for_update() to lock the rows being read
            last_entry = IMP_RMTRRequest.objects.filter(
                imp_rmtr_no__iregex=f'^IMP-{current_year}-[0-9]{{4}}$'
            ).select_for_update().order_by('-imp_rmtr_no').first()
            
            if last_entry:
                try:
                    # Split and validate the number format
                    prefix, year_part, number_part = last_entry.imp_rmtr_no.split('-')
                    
                    # Validate year part matches current year
                    if year_part != str(current_year):
                        logger.warning(f"Year mismatch in imp_rmtr_no: {last_entry.imp_rmtr_no}, using new sequence")
                        new_number = 1
                    else:
                        new_number = int(number_part) + 1
                        
                        # Check for number overflow
                        if new_number > 9999:
                            logger.error("Number sequence exceeded maximum (9999)")
                            return JsonResponse({
                                'status': 'error',
                                'message': 'Number sequence exceeded maximum value'
                            }, status=400)
                            
                except (ValueError, IndexError) as e:
                    logger.error(f"Error parsing imp_rmtr_no: {last_entry.imp_rmtr_no}, Error: {str(e)}")
                    new_number = 1
            else:
                new_number = 1
            
            # Generate new number
            imp_rmtr_number = f'IMP-{current_year}-{str(new_number).zfill(4)}'
            
            # Verify the generated number doesn't already exist
            if IMP_RMTRRequest.objects.filter(imp_rmtr_no=imp_rmtr_number).exists():
                logger.error(f"Generated number already exists: {imp_rmtr_number}")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Generated number already exists in database'
                }, status=409)  # 409 Conflict
            
            logger.info(f"Successfully generated new IMP RMTR number: {imp_rmtr_number}")
            
            # If using DRF, you can return Response instead of JsonResponse
            if request.accepted_renderer.format == 'json':
                return Response({
                    'status': 'success',
                    'imp_rmtr_number': imp_rmtr_number
                })
            
            return JsonResponse({
                'status': 'success',
                'imp_rmtr_number': imp_rmtr_number
            })

    except Exception as e:
        logger.error(f"Error generating IMP RMTR number: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Failed to generate IMP RMTR number',
            'detail': str(e) if settings.DEBUG else None
        }, status=500)



        

@login_required
def imp_submit_form(request):
    try:
        if request.method != 'POST':
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid request method'
            }, status=405)

        form = IMP_RMTRRequestForm(request.POST, request.FILES)
        
        if not form.is_valid():
            return JsonResponse({
                'status': 'error',
                'message': 'Form validation failed',
                'errors': form.errors.as_json()
            }, status=400)

        # Create report instance
        with transaction.atomic():
            report = form.save(commit=False)
            
            # Get and validate supplier
            supplier_instance = form.cleaned_data.get('supplier')
            if not supplier_instance:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Supplier is required.'
                }, status=400)

            # Set report fields
            report.supplier = supplier_instance
            report.requested_by = form.cleaned_data.get('requested-by', request.user.username)
            report.status = 'pending'
            report.sub_category = form.cleaned_data.get('sub_category', '')
            #report.approved_mgt = form.cleaned_data.get('approved-mgt')
            report.tests = request.POST.get('selected_tests', '')

            # Generate IMP RMTR number if needed
            if not report.imp_rmtr_no:
                report.imp_rmtr_no = report.generate_next_imp_rmtr_no()

            # Save the report
            report.save()
            logger.info(f"Created new IMP RMTR: {report.imp_rmtr_no}")

            # Send email notification
            try:
                send_mail(
                    subject='IMP RMTR Report Submitted',
                    message=f'The IMP RMTR report with number {report.imp_rmtr_no} has been created on {report.date} by {report.requested_by}.',
                    from_email='kapaportal@kapa-oil.com',
                    recipient_list=[request.user.email, 
                    'ict@kapa-oil.com',
                    'purchase.user1@kapa-oil.com'
                    ],
                    fail_silently=True
                )
            except Exception as e:
                logger.warning(f"Email notification failed for IMP RMTR {report.imp_rmtr_no}: {str(e)}")

            # Return success response
            return JsonResponse({
                'status': 'success',
                'message': 'IMP RMTR created successfully',
                'imp_rmtr_no': report.imp_rmtr_no,
                'redirect': '/dashboard/'
            })

    except Exception as e:
        logger.error(f"Error in submit_form: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Server error occurred'
        }, status=500)




    
def fetch_material_data(request):
    # Query all materials, their subcategories, and tests
    materials = Material.objects.prefetch_related('subcategories__tests').all()

    # Prepare the response structure
    materials_data = []
    
    for material in materials:
        material_dict = {
            'material': material.name,
            'subcategories': []
        }
        
        for subcategory in material.subcategories.all():
            subcategory_dict = {
                'name': subcategory.name,
                'tests': [tests.name for tests in subcategory.tests.all()]  # List of tests for each subcategory
            }
            material_dict['subcategories'].append(subcategory_dict)
        
        materials_data.append(material_dict)

    return JsonResponse({'materials': materials_data})


def test(request):
    all_reports = IMP_RMTRRequest.objects.all()
    logger.info(all_reports)  # This will log all the report data in the console or log file
    return render(request, 'pending.html', {'pending_reports': all_reports})


@require_http_methods(["GET"])
def generate_imp_rmtr_number(request):
    """Generate next IMP RMTR number"""
    try:
        current_year = timezone.now().year
        prefix = f"IMP-{current_year}-"
        
        with transaction.atomic():  # Prevent race conditions
            last_entry = IMP_RMTRRequest.objects.filter(
                imp_rmtr_no__iregex=f'^IMP-{current_year}-[0-9]{{4}}$'
            ).select_for_update().order_by('-imp_rmtr_no').first()

            if last_entry:
                try:
                    # Split on last hyphen to handle IMP-YYYY-XXXX format
                    number_part = last_entry.imp_rmtr_no.split('-')[-1]
                    new_number = int(number_part) + 1
                except (ValueError, IndexError):
                    logger.error(f"Error parsing imp_rmtr_no: {last_entry.imp_rmtr_no}")
                    new_number = 1
            else:
                new_number = 1

            imp_rmtr_number = f'{prefix}{str(new_number).zfill(4)}'
            logger.info(f"Generated new IMP RMTR number: {imp_rmtr_number}")
            
            return JsonResponse({
                'status': 'success',
                'imp_rmtr_number': imp_rmtr_number
            })

    except Exception as e:
        logger.error(f"Error generating IMP RMTR number: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Failed to generate IMP RMTR number'
        }, status=500)




@api_view(['GET'])
def get_plant_hod_data(request):
    try:
        plants = Plant.objects.all()
        plant_data = []
        
        for plant in plants:
            plant_data.append({
                'id': plant.id,
                'name': plant.name,
                'hod': plant.hod_name if hasattr(plant, 'hod_name') else ''
            })
            
        return JsonResponse(plant_data, safe=False)
        
    except Exception as e:
        logger.error(f"Error fetching plant HOD data: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Failed to fetch plant and HOD data'
        }, status=500)
        
"""
@login_required
def imp_hod_purchase_approval(request, imp_rmtr_no):
    try:
        logger.info(f"Accessing HOD approval for IMP RMTR: {imp_rmtr_no}")
        logger.info(f"User groups: {[g.name for g in request.user.groups.all()]}")

        # Email mapping for approvers
        APPROVER_EMAILS = {
            'Jaivin': 'jaivin@kapa-oil.com',
            'Milan': 'milan@kapa-oil.com',
            'Neev': 'neev@kapa-oil.com',
            'Sid': 'sid@kapa-oil.com'
        }

        # Get the specific report
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)
        
        # Log original report state
        logger.info(f"Report found: IMP RMTR {imp_rmtr_no}, Status: {report.status}")
        
        # Normalize the status with detailed logging
        current_status = normalize_status(report.status)
        logger.info(f"Status normalization: Original='{report.status}' -> Normalized='{current_status}'")

        # Permission check
        if not request.user.groups.filter(name__in=['HOD_PURCHASE', 'ADMIN']).exists():
            logger.warning(f"Permission denied for user: {request.user.username}")
            messages.error(request, 'You do not have permission to access this page')
            return redirect('pending')

        # Check if report is in correct state with detailed logging
        if current_status != 'report_created':
            logger.error(f"Invalid report state for IMP RMTR: {imp_rmtr_no}, Status: {report.status}")
            logger.error(f"Normalized status '{current_status}' does not match expected 'report_created'")
            messages.error(request, f'Invalid report state: {report.status}')
            return redirect('imp_pending')

        if request.method == 'POST':
            # Get form data
            approval_status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            priority = request.POST.get('priority')
            sensitivity = request.POST.get('sensitivity')
            current_time = timezone.now()

            logger.info(f"Processing approval for IMP RMTR {imp_rmtr_no}: {approval_status}")

            # Update report
            report.hod_purchase_priority = priority
            report.hod_purchase_sensitivity = sensitivity
            report.hod_purchase_comments = comments

            if approval_status == 'approved':
                report.hod_purchase_approved = True
                report.hod_purchase_rejected = False
                report.hod_purchase_date_approved = current_time
                report.status = 'Pending: Management 1st Approval'
                logger.info(f"RMTR {imp_rmtr_no} approved, new status: hod_purchase_approved")
            else:
                report.hod_purchase_approved = False
                report.hod_purchase_rejected = True
                report.hod_purchase_date_rejected = current_time
                report.status = 'rejected'
                logger.info(f"RMTR {imp_rmtr_no} rejected")

            report.save()
            logger.info(f"RMTR {imp_rmtr_no} updated successfully")

            # Priority mapping for email
            priority_mapping = {
                "1": "Low",
                "2": "Medium",
                "3": "High",
                1: "Low",
                2: "Medium",
                3: "High"
            }

            # Prepare recipients list
            recipients = [
                'ict@kapa-oil.com',
                request.user.email,
                
                report.created_by.email if report.created_by else None
            ]

            # Add first approver's email if approved
            if approval_status == 'approved' and report.approved_mgt in APPROVER_EMAILS:
                recipients.append(APPROVER_EMAILS[report.approved_mgt])
                logger.info(f"Added first approver email: {APPROVER_EMAILS[report.approved_mgt]}")

            # Filter out None values and remove duplicates
            recipients = list(set(filter(None, recipients)))

            # Prepare email notification
            subject = f'RMTR Report {imp_rmtr_no} - HOD Purchase {approval_status.title()}'
            
            
            #if need be replace the (''') below 
            message = f'''
            RMTR Report {imp_rmtr_no} has been {approval_status} by HOD Purchase.
            
            Details:
            Priority: {priority_mapping.get(priority, 'Unknown')}
            Sensitivity: {sensitivity}
            Comments: {comments}
            
            Approval Route:
            First Approver: {report.approved_mgt.title()}
            {f'Second Approver: {report.second_approver.title()}' if report.second_approver.title() else ''}
            
            Action By: {request.user.get_full_name() or request.user.username}
            Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}
            
            Next Stage: {"Management First Approval" if approval_status == "approved" else "Report Rejected"}
            {f"Action Required: First approver ({report.approved_mgt.title()}) to review" if approval_status == "approved" else ""}

             Raw Material Test Report Link: http://10.0.0.7:8020
            '''

            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=True,
                )
                logger.info(f"Email notification sent for RMTR {imp_rmtr_no}")
            except Exception as e:
                logger.error(f"Error sending email for RMTR {imp_rmtr_no}: {str(e)}")

            return JsonResponse({
                'success': True,
                'message': f'Report {approval_status} successfully'
            })

        context = {
            'report': report,
        }
        logger.info(f"Rendering HOD approval template for RMTR {imp_rmtr_no}")
        return render(request, 'imp_hod_purchase_approval.html', context)

    except Exception as e:
        logger.exception(f"Error in HOD purchase approval for RMTR {imp_rmtr_no}")
        messages.error(request, f'An error occurred: {str(e)}')
        return redirect('imp_pending')



"""



@login_required
def imp_hod_purchase_approval(request, imp_rmtr_no):
    try:
        logger.info(f"Accessing HOD approval for IMP RMTR: {imp_rmtr_no}")
        logger.info(f"User groups: {[g.name for g in request.user.groups.all()]}")

        # Get the specific report with plant details and its attachments
        report = get_object_or_404(IMP_RMTRRequest.objects.select_related('plant'), imp_rmtr_no=imp_rmtr_no)
        attachments = DocumentAttachment.objects.filter(report=report).order_by('-uploaded_at')
        
        # Log original report state
        logger.info(f"Report found: IMP RMTR {imp_rmtr_no}, Status: {report.status}")
        logger.info(f"Found {attachments.count()} attachments for IMP RMTR {imp_rmtr_no}")
        
        # Normalize the status with detailed logging
        current_status = normalize_status(report.status)
        logger.info(f"Status normalization: Original='{report.status}' -> Normalized='{current_status}'")

        # Get plant-specific emails early to handle any potential errors
        recipients = ['peter.busolo@kapa-oil.com', 'purchase.user7@kapa-oil.com', 'purchase.user6@kapa-oil.com','ict@kapa-oil.com']
        if report.plant:
            try:
                plant_emails = report.plant.get_notification_emails()
                recipients.extend(plant_emails)
                logger.info(f"Added plant notification emails for {report.plant.name}: {plant_emails}")
            except Exception as e:
                logger.error(f"Error getting plant notification emails: {str(e)}")

        # Permission check
        if not request.user.groups.filter(name__in=['HOD_PURCHASE', 'ADMIN']).exists():
            logger.warning(f"Permission denied for user: {request.user.username}")
            messages.error(request, 'You do not have permission to access this page')
            return redirect('imp_pending')

        # Check if report is in correct state with detailed logging
        if current_status != 'report_created':
            logger.error(f"Invalid report state for IMP RMTR: {imp_rmtr_no}, Status: {report.status}")
            logger.error(f"Normalized status '{current_status}' does not match expected 'report_created'")
            messages.error(request, f'Invalid report state: {report.status}')
            return redirect('imp_pending')

        if request.method == 'POST':
            try:
                # Get form data
                approval_status = request.POST.get('approval_status')
                comments = request.POST.get('comments')
                priority = request.POST.get('priority')
                sensitivity = request.POST.get('sensitivity')
                current_time = timezone.now()

                logger.info(f"Processing approval for IMP RMTR {imp_rmtr_no}: {approval_status}")

                # Update report within transaction
                with transaction.atomic():
                    # Update report fields
                    report.hod_purchase_priority = priority
                    report.hod_purchase_sensitivity = sensitivity
                    report.hod_purchase_comments = comments

                    if approval_status == 'approved':
                        report.hod_purchase_approved = True
                        report.hod_purchase_rejected = False
                        report.hod_purchase_date_approved = current_time
                        report.status = 'pending: HOD Approval'
                        logger.info(f"IMP RMTR {imp_rmtr_no} approved, new status: hod_purchase_approved")
                    else:
                        report.hod_purchase_approved = False
                        report.hod_purchase_rejected = True
                        report.hod_purchase_date_rejected = current_time
                        report.status = 'rejected'
                        logger.info(f"IMP RMTR {imp_rmtr_no} rejected")

                    report.save()
                    logger.info(f"IMP RMTR {imp_rmtr_no} updated successfully")

                # Priority mapping for email
                priority_mapping = {
                    "1": "Low", "2": "Medium", "3": "High",
                    1: "Low", 2: "Medium", 3: "High"
                }

                # Add additional recipients
                if request.user.email:
                    recipients.append(request.user.email)
                if report.created_by and report.created_by.email:
                    recipients.append(report.created_by.email)

                # Remove duplicates while preserving order
                recipients = list(dict.fromkeys(filter(None, recipients)))
                logger.info(f"Final recipient list for {imp_rmtr_no}: {recipients}")

                # Prepare email notification
                try:
                    subject = f'Imports RMTR Report {imp_rmtr_no} - HOD Imports & Logistics {approval_status.title()}'
                    
                    # Get attachment counts
                    image_count = attachments.filter(file_type='image').count()
                    pdf_count = attachments.filter(file_type='pdf').count()
                    
                    message = f"""
                    Imports RMTR Report {imp_rmtr_no} has been {approval_status} by HOD Imports & Logistics.

                    Details:
                    RMTR Number: {imp_rmtr_no}

                    Material Name: {report.material_name}

                    Material Type: {report.material_type}

                    Supplier: {report.supplier.name if report.supplier else 'N/A'}

                    Plant: {report.plant.name if report.plant else 'N/A'}

                    Priority: {priority_mapping.get(priority, 'Unknown')}

                    Sensitivity: {sensitivity}

                    Comments: {comments}
                    
                    Specifications:
                    Quantity: {report.quantity} {report.uom}
                    Specs: {report.specs if report.specs else 'N/A'}
                    
                    Attachments:
                    Images: {image_count}
                    PDFs: {pdf_count}
                    
                    Action By: {request.user.get_full_name() or request.user.username}
                    Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}
                    
                    Raw Material Test Report Link: http://10.0.0.7:8020
                    """

                    # Send email with proper error handling
                    try:
                        send_mail(
                            subject=subject,
                            message=message,
                            from_email='kapaportal@kapa-oil.local',
                            recipient_list=recipients,
                            fail_silently=True,
                        )
                        logger.info(f"Email notification sent successfully for IMP RMTR {imp_rmtr_no}")
                        logger.info(f"Recipients: {recipients}")
                    except Exception as email_error:
                        logger.error(f"Failed to send email notification for IMP RMTR {imp_rmtr_no}: {str(email_error)}")
                        # Continue execution even if email fails
                        
                except Exception as msg_error:
                    logger.error(f"Error preparing email message for IMP RMTR {imp_rmtr_no}: {str(msg_error)}")

                return JsonResponse({
                    'success': True,
                    'message': f'Report {approval_status} successfully',
                    'redirect_url': '/imp_pending/'
                })

            except Exception as process_error:
                logger.error(f"Error processing approval for IMP RMTR {imp_rmtr_no}: {str(process_error)}")
                return JsonResponse({
                    'success': False,
                    'message': 'An error occurred while processing the approval'
                }, status=500)

        # GET request - render the approval form
        context = {
            'report': report,
            'page_title': 'HOD Purchase Approval',
            'attachments': attachments,
            'images': attachments.filter(file_type='image'),
            'pdfs': attachments.filter(file_type='pdf')
        }
        logger.info(f"Rendering HOD approval template for IMP RMTR {imp_rmtr_no}")
        return render(request, 'imp_hod_purchase_approval.html', context)

    except Exception as e:
        logger.exception(f"Error in HOD purchase approval for IMP RMTR {imp_rmtr_no}")
        messages.error(request, f'An error occurred: {str(e)}')
        return redirect('imp_pending')



@login_required
def edit_imp_rmtr(request, imp_rmtr_no):
    """
    View function to handle editing of IMP RMTR requests.
    """
    try:
        logger.info(f"Accessing IMP RMTR edit for: {imp_rmtr_no}")
        logger.info(f"User groups: {[g.name for g in request.user.groups.all()]}")
        
        # Get the specific report with all its attachments
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)
        attachments = DocumentAttachment.objects.filter(report=report).order_by('-uploaded_at')
        
        # Permission check
        if not request.user.groups.filter(name__in=['HOD_PURCHASE', 'ADMIN']).exists():
            logger.warning(f"Permission denied for user: {request.user.username}")
            return JsonResponse({
                'success': False,
                'message': 'You do not have permission to edit this IMP RMTR'
            }, status=403)
        
        # Check report state
        current_status = normalize_imp_status(report.status)
        if current_status != 'report_created':
            logger.error(f"Invalid report state for editing IMP RMTR: {imp_rmtr_no}, Status: {report.status}")
            return JsonResponse({
                'success': False,
                'message': f'IMP RMTR cannot be edited in its current state: {report.status}'
            }, status=400)

        if request.method == 'POST':
            try:
                with transaction.atomic():
                    # Update basic information
                    report.uom = request.POST.get('uom')
                    report.quantity = request.POST.get('quantity')
                    report.specs = request.POST.get('specs')
                    report.justification = request.POST.get('justification')

                    # Handle deleted attachments
                    deleted_ids = request.POST.get('deleted_attachments', '').split(',')
                    if deleted_ids and deleted_ids[0]:  # Check if there's at least one non-empty id
                        attachments_to_delete = DocumentAttachment.objects.filter(
                            id__in=deleted_ids,
                            report=report
                        )
                        for attachment in attachments_to_delete:
                            # Delete the physical file
                            if attachment.file:
                                try:
                                    attachment.file.delete(save=False)
                                except Exception as e:
                                    logger.error(f"Error deleting file for attachment {attachment.id}: {str(e)}")
                        # Delete the attachment records
                        attachments_to_delete.delete()
                        logger.info(f"Deleted attachments with IDs: {deleted_ids}")

                    # Handle new images
                    for image in request.FILES.getlist('new_images[]'):
                        if image.size > 10 * 1024 * 1024:  # 10MB limit
                            raise ValidationError(f'Image {image.name} exceeds 10MB limit')
                        
                        if image.content_type not in [
                            'image/jpeg', 'image/png', 'image/gif', 'image/bmp',
                            'image/webp', 'image/tiff', 'image/svg+xml'
                        ]:
                            raise ValidationError(f'Invalid image type for {image.name}')
                        
                        attachment = DocumentAttachment(
                            report=report,
                            file=image,
                            file_type='image'
                        )
                        attachment.save()
                        logger.info(f"Added new image attachment: {image.name}")

                    # Handle new PDFs
                    for pdf in request.FILES.getlist('new_pdfs[]'):
                        if pdf.size > 10 * 1024 * 1024:  # 10MB limit
                            raise ValidationError(f'PDF {pdf.name} exceeds 10MB limit')
                        
                        if pdf.content_type != 'application/pdf':
                            raise ValidationError(f'Invalid file type for {pdf.name}')
                        
                        attachment = DocumentAttachment(
                            report=report,
                            file=pdf,
                            file_type='pdf'
                        )
                        attachment.save()
                        logger.info(f"Added new PDF attachment: {pdf.name}")

                    # Handle legacy image field if present
                    if 'image-upload' in request.FILES:
                        if report.image:
                            report.image.delete(save=False)
                        report.image = request.FILES['image-upload']

                    report.save()
                    logger.info(f"Successfully updated Imports RMTR: {imp_rmtr_no}")
                    
                    # Send notification email
                    try:
                        subject = f'Imports RMTR {report.imp_rmtr_no} has been Updated'
                        
                        # Count current attachments after updates
                        current_images = DocumentAttachment.objects.filter(report=report, file_type='image').count()
                        current_pdfs = DocumentAttachment.objects.filter(report=report, file_type='pdf').count()
                        
                        message = f"""
                        Imports RMTR {report.imp_rmtr_no} has been updated by {request.user.get_full_name()}.
                        
                        Date Modified: {timezone.now()}
                        Action By: {request.user.get_full_name() or request.user.username}
                        
                        Current Attachments:
                        Images: {current_images}
                        PDFs: {current_pdfs}
                        
                        Please review the changes.
                        Raw Material Test Report Link: http://10.0.0.7:8020
                        """
                        
                        recipients = [
                            'ict@kapa-oil.com',
                            report.created_by.email,
                            request.user.email
                        ]
                        
                        # Filter out None/empty values and remove duplicates
                        recipients = list(set(filter(None, recipients)))
                        
                        send_mail(
                            subject=subject,
                            message=message,
                            from_email='kapaportal@kapa-oil.local',
                            recipient_list=recipients,
                            fail_silently=True,
                        )
                        logger.info(f"Notification email sent for IMP RMTR {imp_rmtr_no} update")
                    except Exception as e:
                        logger.error(f"Error sending notification email: {str(e)}")
                        # Continue execution even if email fails
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Changes saved successfully'
                    })
                    
            except ValidationError as e:
                logger.error(f"Validation error updating IMP RMTR {imp_rmtr_no}: {str(e)}")
                return JsonResponse({
                    'success': False,
                    'message': str(e)
                }, status=400)
                
            except Exception as e:
                logger.error(f"Error updating IMP RMTR {imp_rmtr_no}: {str(e)}")
                logger.error(traceback.format_exc())
                return JsonResponse({
                    'success': False,
                    'message': f'Error saving changes: {str(e)}'
                }, status=500)

        # GET request - prepare context
        context = {
            'rmtr': report,
            'attachments': attachments,
            'suppliers': Supplier.objects.all(),
            'plants': Plant.objects.all(),
            'uoms': ['Kgs', 'Ltrs', 'Pcs', 'Tonnes', 'Litres', 'Millilitres', 'Grams']
        }
        
        logger.info(f"Rendering edit form for IMP RMTR {imp_rmtr_no}")
        return render(request, 'edit_imp_rmtr.html', context)
        
    except Exception as e:
        logger.exception(f"Error accessing IMP RMTR edit for {imp_rmtr_no}")
        return JsonResponse({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=500)



        
@login_required
def imp_management_approval(request, imp_rmtr_no):  
    
    try:
        # Email mapping for approvers
        APPROVER_EMAILS = {
            'Jaivin': 'jaivin@kapa-oil.com',
            'Milan': 'milan@kapa-oil.com',
            'Neev': 'neev@kapa-oil.com',
            'Sid': 'sid@kapa-oil.com'
        }

        # Get the specific report - changed to IMP_RMTRRequest
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)
        
        # Create priority mapping
        priority_mapping = {
            "1": "Low",
            "2": "Medium",
            "3": "High",
            1: "Low",
            2: "Medium",
            3: "High"
        }

        # Check permissions
        if not request.user.groups.filter(name__in=['MANAGEMENT', 'ADMIN']).exists():
            logger.warning(f"Permission denied for user: {request.user.username}")
            messages.error(request, 'You do not have permission to access this page')
            return redirect('imp_pending')  

        if request.method == 'POST':
            current_time = timezone.now()
            approval_status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            
            logger.info(f"Processing management approval for IMP RMTR {imp_rmtr_no}: {approval_status}")
            
            # Update the report fields
            report.management_comments = comments
            
            if approval_status == 'approved':
                report.management_approved = True
                report.management_rejected = False
                report.management_date_approved = current_time
                report.status = 'Pending: Management 2nd Approval'
                logger.info(f"IMP RMTR {imp_rmtr_no} approved by first management")

                # Prepare recipients for approval - include second approver
                recipients = [
                    'ict@kapa-oil.com',
                    request.user.email
                ]

                # Add second approver's email if exists
                if report.second_approver and report.second_approver in APPROVER_EMAILS:
                    recipients.append(APPROVER_EMAILS[report.second_approver.title()])
                    logger.info(f"Added second approver email: {APPROVER_EMAILS[report.second_approver.title()]}")

            else:
                report.management_approved = False
                report.management_rejected = True
                report.management_date_rejected = current_time
                report.status = 'rejected'
                logger.info(f"IMP RMTR {imp_rmtr_no} rejected by management")

                # For rejection, notify all parties
                recipients = [
                    'ict@kapa-oil.com',
                    request.user.email,
                    report.created_by.email if report.created_by else None
                ]
            
            # Save the report
            report.save()
            logger.info(f"IMP RMTR {imp_rmtr_no} updated successfully")
            
          
            recipients = list(set(filter(None, recipients)))
            
            # Prepare email notification
            subject = f'IMP RMTR {imp_rmtr_no} - Management (first){"Approval" if approval_status == "approved" else "Rejection"}'
            message = f"""
            IMP RMTR Details:
            -------------
            IMP RMTR Number: {imp_rmtr_no}

            Status: {approval_status.title()}

            Material: {report.material_type}

            Supplier: {report.supplier}

            Plant: {report.plant.name if report.plant else 'N/A'}
            
            Management Comments: {comments}
            
            Approval Route:
            First Approver: {report.approved_mgt.title()}
            Second Approver: {report.second_approver.title() if report.second_approver.title() else 'Not Assigned'}
            
            Action By: {request.user.get_full_name() or request.user.username}
            Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}
            
            {"Next Stage: Pending Second Approval" if approval_status == "approved" else "Status: Rejected"}
            {f"Action Required: Second approver ({report.second_approver.title()}) to review" if approval_status == "approved" and report.second_approver.title() else ""}

             Raw Material Test Report Link: http://10.0.0.7:8020
            """
            
            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=True,
                )
                logger.info(f"Email notification sent for IMP RMTR {imp_rmtr_no}")
            except Exception as e:
                logger.error(f"Error sending email: {str(e)}")
            
            return JsonResponse({
                'success': True,
                'message': f'Report {approval_status} successfully'
            })
        
        # For GET requests, prepare the context
        # Convert priority number to text
        priority_value = report.hod_purchase_priority
        priority_display = priority_mapping.get(priority_value, 'Unknown')

        context = {
            'report': report,
            'priority_display': priority_display,
            'sensitivity': report.hod_purchase_sensitivity
        }
        return render(request, 'imp_management_approval.html', context)
        
    except Exception as e:
        logger.exception(f"Error in Management approval for IMP RMTR {imp_rmtr_no}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)


@login_required
def imp_management_approval_2(request, imp_rmtr_no):
    try:
        logger.info(f"Accessing Management 2nd approval for IMP RMTR: {imp_rmtr_no}")
        logger.info(f"User groups: {[g.name for g in request.user.groups.all()]}")

        # Get the specific IMP report
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)
        
        logger.info(f"Report found: IMP RMTR {imp_rmtr_no}, Status: {report.status}")
        
        # Normalize status
        current_status = normalize_status(report.status)
        logger.info(f"Status normalization: Original='{report.status}' -> Normalized='{current_status}'")

        # Permission check
        if not request.user.groups.filter(name__in=['MANAGEMENT', 'ADMIN']).exists():
            logger.warning(f"Permission denied for user: {request.user.username}")
            return JsonResponse({
                'success': False,
                'message': 'You do not have permission to access this page'
            }, status=403)

        # Status check
        if current_status != 'management_approved':
            logger.error(f"Invalid report state for IMP RMTR: {imp_rmtr_no}, Status: {report.status}")
            return JsonResponse({
                'success': False,
                'message': f'Invalid report state: {report.status}'
            }, status=400)

        if request.method == 'POST':
            # Get form data
            approval_status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            current_time = timezone.now()

            logger.info(f"Processing 2nd management approval for IMP RMTR {imp_rmtr_no}: {approval_status}")

            with transaction.atomic():
                if approval_status == 'approved':
                    report.management_approved_2 = True
                    report.management_rejected_2 = False
                    report.management_date_approved_2 = current_time
                    report.status = 'Pending: HOD Approval'  
                    logger.info(f"IMP RMTR {imp_rmtr_no} approved, new status: management_approved_2")
                else:
                    report.management_approved_2 = False
                    report.management_rejected_2 = True
                    report.management_date_rejected_2 = current_time
                    report.status = 'rejected'
                    logger.info(f"IMP RMTR {imp_rmtr_no} rejected")

                report.management_comments_2 = comments
                report.save()

            # Get notification emails based on plant
            try:
                plant = Plant.objects.get(name=report.plant)
                recipients = [
                    'ict@kapa-oil.com',
                    request.user.email
                ]

                # Add plant notification emails if available
                if hasattr(plant, 'get_notification_emails'):
                    plant_emails = plant.get_notification_emails()
                    if isinstance(plant_emails, list):
                        recipients.extend(plant_emails)
                    else:
                        recipients.append(plant_emails)

                # Add HOD email if available
                if plant.hod:
                    try:
                        recipients.append(plant.get_hod_email())
                    except Exception as e:
                        logger.warning(f"Could not get HOD email for plant {plant.name}: {str(e)}")

            except Plant.DoesNotExist:
                recipients = ['ict@kapa-oil.com', request.user.email]
                logger.warning(f"Plant not found for {report.plant}, using default email")

            # Remove duplicates and None values while preserving order
            recipients = list(dict.fromkeys(filter(None, recipients)))

            # Send email notification
            try:
                subject = f'IMP RMTR {imp_rmtr_no} - Management (Second) {"Approval" if approval_status == "approved" else "Rejection"}'
                message = f"""
                IMP RMTR Details:
                -------------
                IMP RMTR Number: {imp_rmtr_no}

                Status: {approval_status.title()}

                Material Name: {report.material_name}

                Material Type: {report.material_type}

                Supplier: {report.supplier}

                Plant: {report.plant.name if report.plant else 'N/A'}
                
                Management (Second) Comments: {comments}
                
                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}
                
                Next Stage: {"HOD Approval Required" if approval_status == "approved" else "Request Rejected"}
                Raw Material Test Report Link: http://10.0.0.7:8020
                """
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=True
                )
                logger.info(f"Email sent successfully for IMP RMTR {imp_rmtr_no} to {recipients}")
            except Exception as e:
                logger.error(f"Failed to send email for IMP RMTR {imp_rmtr_no}: {str(e)}")

            return JsonResponse({
                'success': True,
                'message': f'Report {approval_status} successfully',
                'redirect_url': '/imp_pending/'
            })

        # GET request - render the form
        context = {
            'report': report,
        }
        logger.info(f"Rendering management approval 2 template for IMP RMTR {imp_rmtr_no}")
        return render(request, 'imp_management_approval_2.html', context)

    except IMP_RMTRRequest.DoesNotExist:
        logger.error(f"IMP RMTR {imp_rmtr_no} not found")
        return JsonResponse({
            'success': False,
            'message': f'IMP RMTR {imp_rmtr_no} not found'
        }, status=404)
    except Exception as e:
        logger.exception(f"Error in management approval 2 for IMP RMTR {imp_rmtr_no}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)
        


@login_required
def imp_fm_approval(request, imp_rmtr_no):
    try:
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)
        if not request.user.groups.filter(name__in=['FM', 'ADMIN']).exists():
            messages.error(request, 'You do not have permission to access this page')
            return redirect('imp_pending')

        if request.method == 'POST':
            current_time = timezone.now()
            approval_status = request.POST.get('approval_status')
            comments = request.POST.get('comments')

            # Update report fields
            report.fm_comments = comments
            if approval_status == 'approved':
                report.fm_approved = True
                report.fm_rejected = False
                report.fm_date_approved = timezone.now()
                report.status = 'Pending: HOD Approval'
            elif approval_status == 'rejected':
                report.fm_approved = False
                report.fm_rejected = True
                report.fm_date_rejected = timezone.now()
                report.status = 'rejected'

            report.save()
            logger.info(f"Successfully updated FM approval status for report: {report.imp_rmtr_no}")

            # Get notification emails safely
            try:
                plant = Plant.objects.get(name=report.plant)
                recipients = plant.get_notification_emails(), request.user.email
            except Plant.DoesNotExist:
                recipients = ['ict@kapa-oil.com']
                logger.warning(f"Plant not found for {report.plant}, using default email")

            # Send email notification
            try:
                subject = f'Imports RMTR {imp_rmtr_no} - Factory Manager {"Approval" if approval_status == "approved" else "Rejection"}'
                message = f"""
                Imports RMTR Details:
                -------------
                RMTR Number: {imp_rmtr_no}

                Status: {approval_status.title()}

                Material: {report.material_type}

                Supplier: {report.supplier}

                Plant: {report.plant.name if report.plant else 'N/A'}
                
                Factory Manager Comments: {comments}
                
                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}
                """
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=True
                )
                logger.info(f"Email sent successfully for IMP RMTR {imp_rmtr_no} to {recipients}")
            except Exception as e:
                logger.error(f"Failed to send email for IMP RMTR {imp_rmtr_no}: {str(e)}")

            return JsonResponse({
                'success': True,
                'message': f'Report {approval_status} successfully'
            })

        context = {
            'report': report
        }
        return render(request, 'imp_fm_approval.html', context)

    except Exception as e:
        logger.error(f"Error in FM approval: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'An error occurred during processing'
        }, status=500)
""" 
@login_required
def imp_hod_approval(request, imp_rmtr_no):
    try:
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)
        
        # Check permissions
        if not request.user.groups.filter(name__in=['HOD','HOD_TEST', 'ADMIN']).exists():
            messages.error(request, 'You do not have permission to access this page')
            return redirect('imp_pending')

        if request.method == 'POST':
            status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            current_time = timezone.now()

            # Update report status
            if status == 'approved':
                report.hod_approved = True
                report.hod_rejected = False
                report.status = 'Pending: Lab Test'
                report.hod_date_approved = current_time
            elif status == 'rejected':
                report.hod_approved = False
                report.hod_rejected = True
                report.status = 'rejected'
                report.hod_date_rejected = current_time

            report.hod_comments = comments
            report.save()

            # Send email notification
            try:
                recipients = [
                    'ict@kapa-oil.com',
                    'qao.user18@kapa-oil.com',
                    'qao.user9@kapa-oil.com',
                    'qao.user4@kapa-oil.com',
                    'qao.user7@kapa-oil.com',
                    'qao.user3@kapa-oil.com',
                    'qao.user1@kapa-oil.com',
                    'qao.user2@kapa-oil.com',
                    'qao.user8@kapa-oil.com',
                    request.user.email
                ]

                subject = f'Imports RMTR {imp_rmtr_no} - HOD {Plant} {"Approval" if status == "approved" else "Rejection"}'
                message = f'''
                Imports RMTR Details:
                -------------
                RMTR Number: {imp_rmtr_no}
                Status: {status.upper()}
                Material: {report.material_type}
                Supplier: {report.supplier}
                
                HOD Comments: {comments}
                
                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                 Raw Material Test Report Link: http://10.0.0.7:8020
                '''
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=True
                )
            except Exception as e:
                logger.error(f"Failed to send email for IMP RMTR {imp_rmtr_no}: {str(e)}")

            return JsonResponse({
                'success': True,
                'message': f'Request {status} successfully'
            })

        context = {
            'report': report,
            'page_title': 'HOD Approval'
        }
        return render(request, 'imp_hod_approval.html', context)

    except Exception as e:
        logger.error(f"Error in HOD approval: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'An error occurred while processing your request'
        }, status=500)
"""   




from django.utils import timezone
from datetime import datetime, time, timedelta
import logging
from typing import List, Dict, Optional

class DeadlineConfig:
    """Deadline configurations for different stages"""
    
    # Timeline configurations (in hours)
    RMTR_TIMELINES = {
        'Pending: HOD Purchase Approval': {'hours': 12},
        'Pending: Management 1st Approval': {'hours': 12},
        'Pending: Management 2nd Approval': {'hours': 12},
        'Pending: HOD Approval': {'hours': 12},
        'Pending: Lab Test': {'hours': None},  
        'Pending: QAO Review': {'hours': 12},
        'Pending: HOD Test Approval': {'hours': 12},
        'Pending: Management Test Approval': {'hours': 12}
    }

    IMP_TIMELINES = {
        'Pending: HOD Purchase Approval': {'hours': 12},
        'Pending: HOD Approval': {'hours': 12},
        'Pending: Lab Test': {'hours': None},
        'Pending: QAO Review': {'hours': 12},
        'Pending: HOD Test Approval': {'hours': 12},
        'Pending: Management Test Approval': {'hours': 12}
    }

class EmailConfig:
    """Email configurations for different stages"""
    
    # Base mandatory recipients
    MANDATORY_RECIPIENTS = ['ict@kapa-oil.com', 'logistics.user2@kapa-oil.com']
    
    # Stage-specific recipient configurations for IMP RMTR
    IMP_STAGE_RECIPIENTS = {
        'Pending: HOD Purchase Approval': {
            'fixed_recipients': [
                'purchase.user2@kapa-oil.com',
                'purchase.user10@kapa-oil.com',
                'peter.busolo@kapa-oil.com'
            ],
            'include_creator': True
        },
        'Pending: HOD Approval': {
            'include_plant_hod': True
        },
        'Pending: Lab Test': {
            'fixed_recipients': [
                'qao.user18@kapa-oil.com',
                'qao.user9@kapa-oil.com',
                'qao.user4@kapa-oil.com',
                'qao.user7@kapa-oil.com',
            ]
        },
        'Pending: QAO Review': {
            'fixed_recipients': [
                'qao.user6@kapa-oil.com',
                'qao.user47@kapa-oil.com',
            ]
        },
        'Pending: HOD Test Approval': {
            'include_plant_hod': True
        },
        'Pending: Management Test Approval': {
            'dynamic_approvers': True
        }
    }

    @classmethod
    def get_recipients(cls, status: str, report, is_import: bool = True) -> List[str]:
        """Get email recipients for a specific status"""
        recipients = cls.MANDATORY_RECIPIENTS.copy()
        
        # Get stage config based on report type (always import in this case)
        stage_config = cls.IMP_STAGE_RECIPIENTS.get(status, {})
        
        # Add fixed recipients for the stage
        recipients.extend(stage_config.get('fixed_recipients', []))

        # Add creator's email if needed
        if stage_config.get('include_creator', False) and hasattr(report, 'created_by'):
            if report.created_by and report.created_by.email:
                recipients.append(report.created_by.email)

        # Add plant HOD emails if needed
        if stage_config.get('include_plant_hod', False) and hasattr(report, 'plant'):
            try:
                if report.plant.hod_email:
                    recipients.append(report.plant.hod_email)
                if report.plant.deputy_hod_email:
                    recipients.append(report.plant.deputy_hod_email)
                if hasattr(report.plant, 'get_notification_emails'):
                    plant_emails = report.plant.get_notification_emails()
                    if isinstance(plant_emails, (list, tuple)):
                        recipients.extend(plant_emails)
                    elif isinstance(plant_emails, str):
                        recipients.append(plant_emails)
            except Exception as e:
                logger.error(f"Error getting plant HOD emails: {str(e)}")

        # Add current user if available
        if hasattr(report, 'current_user') and report.current_user and report.current_user.email:
            recipients.append(report.current_user.email)

        # Remove duplicates while preserving order
        return list(dict.fromkeys(filter(None, recipients)))
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.core.mail import send_mail
from django.contrib import messages
from django.db import transaction
from datetime import datetime, time, timedelta
from .models import IMP_RMTRRequest, DocumentAttachment
import logging

logger = logging.getLogger(__name__)

def add_business_days(date, days):
    """Add business days to a date excluding weekends"""
    current_date = date
    remaining_days = days
    
    while remaining_days > 0:
        current_date += timedelta(days=1)
        if current_date.weekday() < 5:  # 0-4 are weekdays
            remaining_days -= 1
    
    return current_date

def calculate_lab_deadline(current_time, days):
    """Calculate lab deadline based on business days"""
    # Start from next business day
    start_date = current_time.date()
    if current_time.hour >= 17:  # If after 5 PM, start from next day
        start_date += timedelta(days=1)
    while start_date.weekday() >= 5:  # Skip weekends
        start_date += timedelta(days=1)
        
    end_date = add_business_days(start_date, days)
    return datetime.combine(end_date, time(17, 0))  # 5 PM on deadline day

def get_business_hours_elapsed(start_time, end_time):
    """Calculate business hours elapsed between two timestamps"""
    current = start_time
    hours = 0
    
    while current < end_time:
        if current.weekday() < 5:  # Weekday
            if 9 <= current.hour < 17:  # Business hours
                hours += 1
        current += timedelta(hours=1)
    
    return hours

@login_required
def imp_hod_approval(request, imp_rmtr_no):
    try:
        logger.info(f"Accessing HOD approval for IMP RMTR: {imp_rmtr_no}")
        logger.info(f"User groups: {[g.name for g in request.user.groups.all()]}")

        # Get report with its attachments
        report = get_object_or_404(IMP_RMTRRequest.objects.select_related('plant'), imp_rmtr_no=imp_rmtr_no)
        attachments = DocumentAttachment.objects.filter(report=report).order_by('-uploaded_at')
        
        logger.info(f"Found {attachments.count()} attachments for IMP RMTR {imp_rmtr_no}")
        
        # Check permissions
        if not request.user.groups.filter(name__in=['HOD', 'HOD_TEST', 'ADMIN']).exists():
            logger.warning(f"Permission denied for user: {request.user.username}")
            messages.error(request, 'You do not have permission to access this page')
            return redirect('imp_pending')

        if request.method == 'POST':
            try:
                status = request.POST.get('approval_status')
                comments = request.POST.get('comments')
                lab_timeline_days = request.POST.get('labtimelines')
                current_time = timezone.now()

                # Calculate time taken for approval
                if hasattr(report, 'last_status_change') and report.last_status_change:
                    hours_taken = get_business_hours_elapsed(report.last_status_change, current_time)
                    timeline_config = DeadlineConfig.IMP_TIMELINES.get(report.status, {'hours': 12})
                    was_delayed = hours_taken > timeline_config['hours']
                    
                    timeline_info = f"""
                    Timeline Information:
                    -------------------
                    Time Taken: {round(hours_taken, 1)} business hours
                    Expected Timeline: {timeline_config['hours']} business hours
                    Status: {'Process DELAYED' if was_delayed else 'Within Timeline'}
                    """
                else:
                    timeline_info = "Timeline tracking has been started"

                # Validate lab timeline for approval
                if status == 'approved' and not lab_timeline_days:
                    return JsonResponse({
                        'success': False,
                        'message': 'Please select lab timeline before approving'
                    }, status=400)

                with transaction.atomic():
                    # Update report status
                    if status == 'approved':
                        report.hod_approved = True
                        report.hod_rejected = False
                        report.status = 'Pending: Lab Test'
                        report.hod_date_approved = current_time
                        report.last_status_change = current_time

                        # Set lab timeline and deadline
                        try:
                            days = int(lab_timeline_days)
                            if 1 <= days <= 10:
                                report.lab_timeline_days = days
                                report.lab_deadline = calculate_lab_deadline(current_time, days)
                                logger.info(f"Lab timeline set: {days} days, deadline: {report.lab_deadline}")
                            else:
                                report.lab_timeline_days = 3
                                report.lab_deadline = calculate_lab_deadline(current_time, 3)
                                logger.warning(f"Invalid lab timeline ({days}), using default (3 days)")
                        except (ValueError, TypeError) as e:
                            logger.error(f"Error setting lab timeline: {str(e)}")
                            report.lab_timeline_days = 3
                            report.lab_deadline = calculate_lab_deadline(current_time, 3)

                    else:  # rejected
                        report.hod_approved = False
                        report.hod_rejected = True
                        report.status = 'rejected'
                        report.hod_date_rejected = current_time
                        report.last_status_change = current_time

                    report.hod_comments = comments
                    report.hod_by = request.user
                    report.save()

                    # Prepare attachments info for email
                    image_count = attachments.filter(file_type='image').count()
                    pdf_count = attachments.filter(file_type='pdf').count()
                    attachments_info = f"\nAttachments:\nImages: {image_count}\nPDFs: {pdf_count}"

                    # Add timeline info for email
                    if status == 'approved' and hasattr(report, 'lab_deadline'):
                        timeline_info += f"""
                        Lab Timeline:
                        ------------
                        Days Allocated: {report.lab_timeline_days} business days
                        Deadline: {report.lab_deadline.strftime('%Y-%m-%d %H:%M')}
                        """

                    # Get recipients using EmailConfig
                    report.current_user = request.user  # Set current user for email config
                    recipients = EmailConfig.get_recipients(report.status, report, is_import=True)
                    logger.info(f"Final recipient list for {imp_rmtr_no}: {recipients}")

                    subject = f'Imports RMTR {imp_rmtr_no} - HOD {report.plant.name} {"Approval" if status == "approved" else "Rejection"}'
                    message = f"""
                    Imports RMTR Details:
                    -------------
                    RMTR Number: {imp_rmtr_no}
                    Status: {status.title()}
                    Material: {report.material_type}
                    Supplier: {report.supplier.name if report.supplier else 'N/A'}
                    Tests To Be Carried Out: {report.tests}
                    
                    HOD Comments: {comments}
                    
                    {timeline_info}
                    
                    Action By: {request.user.get_full_name() or request.user.username}
                    Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}
                    {attachments_info}
                    
                    Raw Material Test Report Link: http://10.0.0.7:8020
                    """

                    try:
                        send_mail(
                            subject=subject,
                            message=message,
                            from_email='kapaportal@kapa-oil.local',
                            recipient_list=recipients,
                            fail_silently=True
                        )
                        logger.info(f"Email notification sent successfully for IMP RMTR {imp_rmtr_no}")
                    except Exception as e:
                        logger.error(f"Failed to send email for IMP RMTR {imp_rmtr_no}: {str(e)}")

                    return JsonResponse({
                        'success': True,
                        'message': f'Request {status} successfully',
                        'redirect_url': '/imp_pending/'
                    })

            except Exception as process_error:
                logger.error(f"Error processing approval for IMP RMTR {imp_rmtr_no}: {str(process_error)}")
                return JsonResponse({
                    'success': False,
                    'message': 'An error occurred while processing the approval'
                }, status=500)

        # Prepare context for GET request
        context = {
            'report': report,
            'attachments': attachments,
            'images': attachments.filter(file_type='image'),
            'pdfs': attachments.filter(file_type='pdf'),
            'page_title': 'HOD Approval',
            'lab_timeline_options': [
                {'days': i, 'display': f'{i} {"day" if i == 1 else "days"}'}
                for i in range(1, 11)
            ],
            'default_lab_timeline': 3
        }
        logger.info(f"Rendering HOD approval template for IMP RMTR {imp_rmtr_no}")
        return render(request, 'imp_hod_approval.html', context)

    except Exception as e:
        logger.exception(f"Error in HOD approval for IMP RMTR {imp_rmtr_no}")
        messages.error(request, f'An error occurred: {str(e)}')
        return redirect('imp_pending')




@login_required
def imp_fill_page(request, imp_rmtr_no):
    """Handle IMP RMTR test results form"""
    try:
        # Get IMP RMTR request
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)
        
        # Check permissions
        if not request.user.groups.filter(name__in=['LAB', 'ADMIN']).exists():
            messages.error(request, 'You do not have permission to access this page')
            return redirect('imp_pending')

        # Handle form submission
        if request.method == 'POST':
            try:
                # Validate required fields
                lab_qc_comments = request.POST.get('lab_qc_comments', '').strip()
                tests_done_by = request.POST.get('tests_done_by', '').strip()

                if not lab_qc_comments:
                    return JsonResponse({
                        'success': False,
                        'message': 'Please provide lab QC comments'
                    }, status=400)

                if not tests_done_by:
                    return JsonResponse({
                        'success': False,
                        'message': 'Please specify who performed the tests'
                    }, status=400)

                # Process test data
                test_data = []
                test_count = 0

                # First pass: collect and validate test data
                for i in range(1, 17):
                    test_name = request.POST.get(f'tests_carried_out{i}', '').strip()
                    if test_name:
                        test_info = {
                            'index': i,
                            'test': test_name,
                            'sample': request.POST.get(f'sample_results{i}', '').strip(),
                            'raw_material': request.POST.get(f'raw_material_results{i}', '').strip(),
                            'standards': request.POST.get(f'kapa_standards{i}', '').strip()
                        }
                        
                        # Validate test data completeness
                        if not all([test_info['sample'], test_info['raw_material'], test_info['standards']]):
                            return JsonResponse({
                                'success': False,
                                'message': f'Incomplete data for test "{test_name}". All fields are required.'
                            }, status=400)
                            
                        test_data.append(test_info)
                        test_count += 1

                if test_count == 0:
                    return JsonResponse({
                        'success': False,
                        'message': 'At least one test result is required'
                    }, status=400)

                # Validate image if uploaded
                if 'test_image' in request.FILES:
                    is_valid, error = validate_image(request.FILES['test_image'])
                    if not is_valid:
                        return JsonResponse({
                            'success': False,
                            'message': error
                        }, status=400)

                # Save all data
                try:
                    # Clear existing test data
                    for i in range(1, 17):
                        setattr(report, f'tests_carried_out{i}', '')
                        setattr(report, f'sample_results{i}', '')
                        setattr(report, f'raw_material_results{i}', '')
                        setattr(report, f'kapa_standards{i}', '')

                    # Save new test data
                    for test in test_data:
                        i = test['index']
                        setattr(report, f'tests_carried_out{i}', test['test'])
                        setattr(report, f'sample_results{i}', test['sample'])
                        setattr(report, f'raw_material_results{i}', test['raw_material'])
                        setattr(report, f'kapa_standards{i}', test['standards'])
                        logger.debug(f"Saved test {i}: {test['test']}")

                    # Save other fields
                    report.lab_qc_comments = lab_qc_comments
                    report.tests_done_by = tests_done_by

                    # Handle image upload
                    if 'test_image' in request.FILES:
                        success, error = handle_image_upload(report, request.FILES['test_image'])
                        if not success:
                            return JsonResponse({
                                'success': False,
                                'message': error
                            }, status=400)

                    # Update status and save
                    report.status = 'Pending QAO review'
                    report.save()

                    # Create HTML email with tables
                    html_message = f"""
                    <html>
                    <head>
                        <style>
                            body {{
                                font-family: Arial, sans-serif;
                                max-width: 780px;
                                margin: 0 auto;
                            }}
                            table {{
                                border-collapse: collapse;
                                width: 80%;
                                margin-bottom: 15px;
                                margin-left: auto;
                                margin-right: auto;
                            }}
                            th, td {{
                                border: 1px solid #ddd;
                                padding: 5px 8px;
                                text-align: left;
                                font-size: 14px;
                            }}
                            th {{
                                background-color: #f2f2f2;
                                font-weight: bold;
                            }}
                            tr:nth-child(even) {{
                                background-color: #f9f9f9;
                            }}
                            .header-table {{
                                width: 65%;
                                margin-bottom: 20px;
                            }}
                            .section-title {{
                                font-weight: bold;
                                font-size: 16px;
                                margin-top: 15px;
                                margin-bottom: 5px;
                                text-align: left;
                                padding-left: 7.5%;
                            }}
                        </style>
                    </head>
                    <body>
                        <h2 style="text-align: center;">Lab Test Results for Imports RMTR NO: {report.imp_rmtr_no}</h2>
                        <table class="header-table">
                            <tr>
                                <th>Plant</th>
                                <td>{report.plant.name if report.plant else 'N/A'}</td>
                            </tr>
                            <tr>
                                <th>Number of Tests</th>
                                <td>{test_count}</td>
                            </tr>
                            <tr>
                                <th>Tests Performed By</th>
                                <td>{tests_done_by}</td>
                            </tr>
                            <tr>
                                <th>Submission Date</th>
                                <td>{timezone.now().strftime("%Y-%m-%d %H:%M:%S")}</td>
                            </tr>
                            <tr>
                                <th>Action By</th>
                                <td>{request.user.get_full_name() or request.user.username}</td>
                            </tr>
                        </table>

                        <div class="section-title">Lab QC Comments:</div>
                        <table>
                            <tr>
                                <td>{lab_qc_comments}</td>
                            </tr>
                        </table>

                        <div class="section-title">Test Results:</div>
                        <table>
                            <tr>
                                <th>Test</th>
                                <th>Sample Results</th>
                                <th>Current Raw Material Results</th>
                                <th>KAPA Standards</th>
                            </tr>
                    """

                    # Add each test result as a row in the table
                    for test in test_data:
                        html_message += f"""
                            <tr>
                                <td>{test['test']}</td>
                                <td>{test['sample']}</td>
                                <td>{test['raw_material']}</td>
                                <td>{test['standards']}</td>
                            </tr>
                        """

                    # Close the HTML
                    html_message += f"""
                        </table>
                        <p style="text-align: center;">Raw Material Test Report Link: <a href="http://10.0.0.7:8020">http://10.0.0.7:8020</a></p>
                    </body>
                    </html>
                    """

                    # Also create a plain text message for clients that don't support HTML
                    plain_message = f"""
Lab test results for Imports RMTR NO: {report.imp_rmtr_no}

Plant: {report.plant.name if report.plant else 'N/A'}
Number of Tests: {test_count}
Tests Performed By: {tests_done_by}
Submission Date: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}

Lab QC Comments:
{lab_qc_comments}

Test Results:
"""
                    for test in test_data:
                        plain_message += f"""
Test: {test['test']}
Sample Results: {test['sample']}
Current Raw Material Results: {test['raw_material']}
KAPA Standards: {test['standards']}
---------------------------"""

                    plain_message += f"""

Action By: {request.user.get_full_name() or request.user.username}

Raw Material Test Report Link: http://10.0.0.7:8020
"""
                    
                    recipients = [
                        
                        request.user.email,
                        'qao.user6@kapa-oil.com',
                        'qao.user47@kapa-oil.com',
                        'peter.busolo@kapa-oil.com',
                        'ict@kapa-oil.com'
                    ]

                    # Subject for the email
                    subject = f'Lab Test Results - Imports RMTR {report.imp_rmtr_no}'

                    try:
                        # Send HTML email with fallback to plain text
                        from django.core.mail import EmailMultiAlternatives
                        
                        email = EmailMultiAlternatives(
                            subject=subject,
                            body=plain_message,
                            from_email='kapaportal@kapa-oil.local',
                            to=recipients
                        )
                        email.attach_alternative(html_message, "text/html")
                        email.send(fail_silently=True)
                        
                    except Exception as e:
                        logger.error(f"Error sending email: {str(e)}")
                        # Fall back to plain text email if HTML email fails
                        try:
                            send_mail(
                                subject=subject,
                                message=plain_message,
                                from_email='kapaportal@kapa-oil.local',
                                recipient_list=recipients,
                                fail_silently=True,
                            )
                        except Exception as e:
                            logger.error(f"Error sending fallback email: {str(e)}")

                    return JsonResponse({
                        'success': True,
                        'message': f'Successfully saved {test_count} test results'
                    })

                except Exception as e:
                    logger.error(f"Error saving data: {str(e)}")
                    return JsonResponse({
                        'success': False,
                        'message': 'Error saving data to database'
                    }, status=500)

            except Exception as e:
                logger.error(f"Error processing form submission: {str(e)}")
                return JsonResponse({
                    'success': False,
                    'message': f'Error processing form submission: {str(e)}'
                }, status=500)

        # Handle GET request
        context = {
            'form_data': report,
            'page_title': 'Lab Test Results Form',
            'can_edit': report.status in ['hod_approved', 'pending']
        }
        
        return render(request, 'imp_fill_page.html', context)

    except Exception as e:
        logger.error(f"Error in fill_page view: {str(e)}")
        messages.error(request, 'Error accessing the test form')
        return redirect('imp_pending')
    





    
def handle_image_upload(report, image):
    """Handle image upload for IMP RMTR reports"""
    try:
        # Check if we're dealing with an IMP_RMTRRequest
        if isinstance(report, IMP_RMTRRequest):
            report_number = report.imp_rmtr_no
            upload_path = f'imp/test_images/imp_{report_number}'
        else:
            report_number = report.rmtr_no
            upload_path = f'test_images/rmtr_{report_number}'

        # Validate image type and size
        if not image.content_type.startswith('image/'):
            return False, 'Invalid file type. Only images are allowed.'
        
        if image.size > 5 * 1024 * 1024:  # 5MB limit
            return False, 'Image size too large. Maximum size is 5MB.'
            
        # Create a unique filename
        extension = image.name.split('.')[-1].lower()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'{timestamp}.{extension}'
        
        # Set the complete upload path
        full_path = os.path.join(upload_path, filename)
        
        # Save the image
        report.test_image.save(full_path, image, save=True)
        
        return True, None
        
    except Exception as e:
        logger.error(f"Error handling image upload: {str(e)}")
        return False, f'Error uploading image: {str(e)}'
    
    
def save(self, *args, **kwargs):
    # Generate IMP number if not set
    if not self.imp_rmtr_no:
        self.imp_rmtr_no = self.generate_next_imp_rmtr_no()
    
    # Ensure image is saved according to imp_rmtr_no (if IMP number exists)
    if self.imp_rmtr_no:
        if self.image and hasattr(self.image, 'name'):
            self.image.name = f"imp/images/imp_{self.imp_rmtr_no}/{self.image.name.split('/')[-1]}"
        if self.test_image and hasattr(self.test_image, 'name'):
            self.test_image.name = f"imp/test_images/imp_{self.imp_rmtr_no}/{self.test_image.name.split('/')[-1]}"
    
    # Fix the super() call by using either:
    #super().__class__.save(self, *args, **kwargs)  # Modern way
    # OR
    super(IMP_RMTRRequest, self).save(*args, **kwargs)  # Traditional way
    
    
 
 
 
 
 
 
 
 
 
 
 
 
 
 
        
# Test Results Submission View
def submit_test_results(request, imp_rmtr_no):
    report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)

    if request.method == 'POST':
        form = TestResultsForm(request.POST)
        if form.is_valid():
            test_result = form.save(commit=False)
            test_result.report = report
            test_result.save()

            # Update RMTRRequest status
            report.status = 'Test Done'
            report.save()

            # Send email notification
            send_mail(
                subject='Test Results Submitted',
                message=f'The test results for RMTR request {imp_rmtr_no} have been submitted.',
                from_email='ict@kapa-oil.com',
                recipient_list=[report.created_by.email],
                fail_silently=False,
            )

            messages.success(request, 'Test results submitted successfully.')
            return redirect('next_stage_view')  # Redirect to the next approval stage

    else:
        form = TestResultsForm()

    return render(request, 'imp_fill_page.html', {'form': form, 'report': report})

@login_required
def imp_retest_request(request, imp_rmtr_no):
    try:
        logger.info(f"Accessing retest request for IMP RMTR: {imp_rmtr_no}")

        # Get the report
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)

        # Check permissions
        if not request.user.groups.filter(name__in=['QAO', 'HOD_TEST', 'FM_TEST', 'MANAGEMENT_TEST', 'ADMIN']).exists():
            messages.error(request, 'You do not have permission to request a retest.')
            logger.warning(f"Permission denied for user: {request.user.username}")
            return redirect('pending')

        if request.method == 'POST':
            try:
                # Get form data
                retest_reason = request.POST.get('retest_reason')
                comments = request.POST.get('comments')
                current_time = timezone.now()

                # Validate retest_reason
                if not retest_reason or not retest_reason.strip():
                    logger.error("Invalid retest reason provided")
                    return JsonResponse({
                        'success': False,
                        'message': 'Please provide a valid reason for retest.'
                    }, status=400)

                logger.info(f"Processing retest request for IMP RMTR: {imp_rmtr_no}")

                with transaction.atomic():
                    # Store previous state
                    previous_status = report.status

                    # Update report
                    report.retest_requested_by = request.user
                    report.retest_requested_date = current_time
                    report.retest_reason = retest_reason.strip()
                    report.previous_status = previous_status
                    report.status = 'Pending: Retest'
                    report.retest_stage = 'requested'
                    
                    # Reset approval flags to allow re-approval after retest
                    report.qao_approved = False
                    report.hod_test_approved = False
                    report.fm_test_approved = False
                    report.management_test_approved = False
                    report.qao_date_approved = None
                    report.hod_test_date_approved = None
                    report.fm_test_date_approved = None
                    report.management_test_date_approved = None
                    
                    report.save()

                    # Base recipient list with mainstay recipients
                    base_recipients = [
                        'ict@kapa-oil.com',
                        'qao.user18@kapa-oil.com',
                        'qao.user9@kapa-oil.com',
                        'qao.user4@kapa-oil.com',
                        'qao.user7@kapa-oil.com',
                        'qao.user3@kapa-oil.com',
                        'qao.user50@kapa-oil.com',
                        'qao.user28@kapa-oil.com',
                        'qao.user47@kapa-oil.com',
                        request.user.email
                    ]

                    # Add role-specific recipients
                    additional_recipients = []
                    if request.user.groups.filter(name='QAO').exists():
                        # append() accepts a single item; use extend() for multiple recipients
                        additional_recipients.extend(['qao.user6@kapa-oil.com', 'qao.user47@kapa-oil.com'])
                    elif request.user.groups.filter(name='HOD_TEST').exists():
                        # No extra recipients configured for this role
                        pass
                    elif request.user.groups.filter(name='FM_TEST').exists():
                        # No extra recipients configured for this role
                        pass
                    elif request.user.groups.filter(name='MANAGEMENT_TEST').exists():
                        additional_recipients.append('qao.user6@kapa-oil.com')

                    # Combine and deduplicate recipient lists
                    recipient_list = list(set(base_recipients + additional_recipients))

                    # Prepare email content
                    subject = f'Imports RMTR {imp_rmtr_no} - Retest Requested'
                    message = f"""
                    Imports RMTR Details:
                    -------------
                    RMTR Number: {imp_rmtr_no}

                    Status: Pending Retest
                    Material: {report.material_type}

                    Supplier: {report.supplier}

                    Plant: {report.plant.name if report.plant else 'N/A'}
                    
                    Retest Reason: {retest_reason}
                    Comments: {comments}
                    
                    Requested By: {request.user.get_full_name() or request.user.username}
                    Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                     Raw Material Test Report Link: http://10.0.0.7:8020
                    """

                    send_mail(
                        subject=subject,
                        message=message,
                        from_email='kapaportal@kapa-oil.local',
                        recipient_list=recipient_list,
                        fail_silently=True
                    )

                return JsonResponse({
                    'success': True,
                    'message': 'Retest request submitted successfully.',
                    'redirect_url': '/imp_pending/'
                })
            

            except Exception as inner_e:
                logger.error(f"Error processing retest request: {str(inner_e)}")
                return JsonResponse({
                    'success': False,
                    'message': 'Error processing retest request'
                }, status=500)

        # GET request - render template
        context = {
            'report': report,
            'page_title': 'Request Retest',
            'imp_rmtr_no': imp_rmtr_no  # Added this to ensure template has access
        }

        return render(request, 'imp_retest_request.html', context)

    except Exception as e:
        logger.exception(f"Error in retest_request: {str(e)}")
        messages.error(request, f'An error occurred: {str(e)}')
        return redirect('imp_pending')

def handle_retest_request(request, report, data):
    """Handle initial retest request"""
    retest_reason = data.get('retest_reason', '').strip()
    comments = data.get('comments', '').strip()

    if not retest_reason:
        return JsonResponse({
            'success': False,
            'message': 'Please provide a reason for retest.'
        }, status=400)

    # Create retest request
    retest = RetestRequest.objects.create(
        imp_rmtr_no=report,  # Changed from rmtr to imp_rmtr_no
        requested_by=request.user,
        reason=retest_reason,
        comments=comments,
        original_status=report.status
    )

    # Update report status
    report.retest_requested_by = request.user
    report.retest_requested_date = timezone.now()
    report.status = 'Pending: Retest'
    report.save()

    # Send notification email
    send_retest_notification(request, report, retest)

    return JsonResponse({
        'success': True,
        'message': 'Retest request submitted successfully.',
        'redirect_url': '/imp_pending/'
    })

def handle_retest_results(request, report, data):
    """Handle retest results submission"""
    test_data = {}
    
    # Collect test data
    for i in range(1, 17):
        test_name = data.get(f'tests_carried_out{i}')
        if test_name:
            test_data[str(i)] = {
                'test': test_name,
                'sample': data.get(f'sample_results{i}'),
                'raw_material': data.get(f'raw_material_results{i}'),
                'standards': data.get(f'kapa_standards{i}')
            }

    if not test_data:
        return JsonResponse({
            'success': False,
            'message': 'At least one test result is required'
        }, status=400)

    # Get latest retest request
    retest = RetestRequest.objects.filter(imp_rmtr=report, completed=False).latest('requested_at')
    
    # Update retest data
    retest.test_data = test_data
    retest.completed = True
    retest.save()

    # Update report
    report.status = 'retest_completed'
    report.save()

    # Send completion notification
    send_retest_completion_notification(request, report, retest)

    return JsonResponse({
        'success': True,
        'message': 'Retest results submitted successfully.',
        'redirect_url': '/imp_pending/'
    })

def send_retest_notification(request, report, retest):
    """Send retest request notification"""
    subject = f'RMTR {report.imp_rmtr_no} - Retest Requested'
    message = f"""
    RMTR Details:
    -------------
    RMTR Number: {report.imp_rmtr_no}

    Status: Pending Retest
    Material: {report.material_type}

    Supplier: {report.supplier}

    Plant: {report.plant.name if report.plant else 'N/A'}
    
    Retest Reason: {retest.reason}

    Additional Comments: {retest.comments}
    
    Requested By: {request.user.get_full_name() or request.user.username}
    Date: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}

     Raw Material Test Report Link: http://10.0.0.7:8020
    """

    # Build recipient list based on user's group
    recipient_list = ['qc@kapa-oil.com']
    user_groups = request.user.groups.all()
    
    if any(g.name == 'QAO' for g in user_groups):
        recipient_list.extend(['qao@kapa-oil.com'])
    elif any(g.name == 'HOD_TEST' for g in user_groups):
        recipient_list.extend(['hod_test@kapa-oil.com', 'qao@kapa-oil.com'])
    elif any(g.name == 'FM_TEST' for g in user_groups):
        recipient_list.extend(['fm_test@kapa-oil.com', 'hod_test@kapa-oil.com', 'qao@kapa-oil.com'])
    elif any(g.name == 'MANAGEMENT_TEST' for g in user_groups):
        recipient_list.extend([
            'ict@kapa-oil.com',
            'fm_test@kapa-oil.com',
            'hod_test@kapa-oil.com',
            'qao@kapa-oil.com'
        ])

    send_mail(
        subject=subject,
        message=message,
        from_email='kapaportal@kapa-oil.local',
        recipient_list=list(set(recipient_list)),
        fail_silently=True
    )

def send_retest_completion_notification(request, report, retest):
    """Send retest completion notification"""
    # Format test results for email
    test_results = "\nTest Results:\n-------------\n"
    for test_num, data in retest.test_data.items():
        test_results += f"""
        Test: {data['test']}
        Sample Results: {data['sample']}
        Raw Material Results: {data['raw_material']}
        Standards: {data['standards']}
        -------------
        """

    subject = f'RMTR {report.imp_rmtr_no} - Retest Completed'
    message = f"""
    RMTR Details:
    -------------
    RMTR Number: {report.imp_rmtr_no}
    Material: {report.material_type}
    Supplier: {report.supplier}
    Plant: {report.plant.name if report.plant else 'N/A'}

    {test_results}
    
    Originally Requested By: {retest.requested_by.get_full_name() or retest.requested_by.username}
    Completed By: {request.user.get_full_name() or request.user.username}
    Date: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}

     Raw Material Test Report Link: http://10.0.0.7:8020
    """

    # Send to original requestor and relevant chain
    recipient_list = ['qc@kapa-oil.com']
    if retest.requested_by:
        recipient_list.append(retest.requested_by.email)
        
    # Add others in chain
    requestor_groups = retest.requested_by.groups.all() if retest.requested_by else []
    if any(g.name == 'MANAGEMENT_TEST' for g in requestor_groups):
        recipient_list.extend(['fm_test@kapa-oil.com', 'hod_test@kapa-oil.com', 'qao@kapa-oil.com'])
    elif any(g.name == 'FM_TEST' for g in requestor_groups):
        recipient_list.extend(['hod_test@kapa-oil.com', 'qao@kapa-oil.com'])
    elif any(g.name == 'HOD_TEST' for g in requestor_groups):
        recipient_list.extend(['qao@kapa-oil.com'])

    send_mail(
        subject=subject,
        message=message,
        from_email='kapaportal@kapa-oil.local',
        recipient_list=list(set(recipient_list)),
        fail_silently=True
    )

 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
    
logger = logging.getLogger(__name__)
@login_required
def imp_qao_test_approval(request, imp_rmtr_no):
    try:
        # Changed from RMTRRequest to IMP_RMTRRequest and rmtr_no to imp_rmtr_no
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)

        # Permission check
        if not request.user.groups.filter(name__in=['QAO', 'ADMIN']).exists():
            messages.error(request, 'You do not have permission to access this page.')
            logger.warning(f"Permission denied for user {request.user.username}.")
            return redirect('pending')

        if request.method == 'POST':
            # Handle image upload if present
            if 'test_image' in request.FILES:
                try:
                    # Delete old image if it exists and isn't the default
                    if report.test_image and 'default.jpg' not in report.test_image.name:
                        try:
                            report.test_image.delete(save=False)
                        except Exception as e:
                            logger.warning(f"Failed to delete old image for IMP RMTR {imp_rmtr_no}: {str(e)}")
                    
                    # Save new image
                    report.test_image = request.FILES['test_image']
                    report.save()
                    
                    logger.info(f"Successfully updated test image for IMP RMTR {imp_rmtr_no}")
                    return JsonResponse({
                        'success': True,
                        'message': 'Test image updated successfully',
                        'image_url': report.test_image.url
                    })
                except Exception as img_error:
                    logger.error(f"Error updating test image for IMP RMTR {imp_rmtr_no}: {str(img_error)}")
                    return JsonResponse({
                        'success': False,
                        'message': 'Failed to update test image'
                    }, status=500)

            # Handle approval process
            approval_status = request.POST.get('approval_status')
            comments = request.POST.get('comments', '').strip()
            current_time = timezone.now()

            # Validate approval_status
            if not approval_status or approval_status not in ['approved', 'rejected']:
                logger.error("Invalid approval status provided.")
                return JsonResponse({'success': False, 'message': 'Invalid approval status'}, status=400)

            logger.info(f"Processing QAO approval for IMP RMTR {imp_rmtr_no} with status: {approval_status}.")

            try:
                with transaction.atomic():
                    # Update report based on the action
                    if approval_status == 'approved':
                        report.qao_approved = True
                        report.qao_rejected = False
                        report.qao_date_approved = current_time
                        report.status = 'Pending: HOD Test Approval'
                    elif approval_status == 'rejected':
                        # Modified to continue the process despite rejection
                        report.qao_approved = False
                        report.qao_rejected = True
                        report.qao_date_rejected = current_time
                        # Continue to HOD Test Approval instead of terminating with 'rejected' status
                        report.status = 'Pending: HOD Test Approval'

                    report.qao_comments = comments
                    report.save()

                # Get notification emails based on plant
                try:
                    plant = Plant.objects.get(name=report.plant)
                    recipients = plant.get_notification_emails()
                    if request.user.email:
                        recipients.append(request.user.email)
                except Plant.DoesNotExist:
                    recipients = ['ict@kapa-oil.com']
                    logger.warning(f"Plant not found for {report.plant}, using default email")

                # Send email notification
                try:
                    subject = f'Imports RMTR {imp_rmtr_no} - QAO {approval_status.title()}'
                    
                    # Update message status to indicate that process continues despite rejection
                    message_status = "Approved" if approval_status == "approved" else "Rejected (Process Continuing to HOD Test Approval)"
                    
                    message = f"""
                    Imports RMTR Details:
                    -------------
                    RMTR Number: {imp_rmtr_no}

                    Status: {message_status}

                    Material Name: {report.material_name}

                    Material Type: {report.material_type}
                    Supplier: {report.supplier}

                    Plant: {report.plant}
                    
                    QAO Comments: {comments}
                    
                    Action By: {request.user.get_full_name() or request.user.username}
                    Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                    Next Stage: HOD Test Approval

                    Raw Material Test Report Link: http://10.0.0.7:8020
                    """

                    send_mail(
                        subject=subject,
                        message=message,
                        from_email='kapaportal@kapa-oil.local',
                        recipient_list=recipients,
                        fail_silently=True,
                    )
                    logger.info(f"Email sent successfully for IMP RMTR {imp_rmtr_no} to {recipients}")
                except Exception as email_error:
                    logger.error(f"Failed to send email for IMP RMTR {imp_rmtr_no}: {str(email_error)}")

                return JsonResponse({
                    'success': True, 
                    'message': f'Request {approval_status} successfully. Process will continue to HOD Test Approval.', 
                    'redirect_url': '/imp_pending/'
                })

            except Exception as db_error:
                logger.error(f"Database error while processing QAO approval for IMP RMTR {imp_rmtr_no}: {str(db_error)}")
                return JsonResponse({
                    'success': False, 
                    'message': 'An error occurred while processing the request.'
                }, status=500)

        # Render template for GET request
        context = {
            'report': report,
            'page_title': 'QAO Test Approval'
        }
        return render(request, 'imp_qao_test_approval.html', context)

    except Exception as e:
        logger.exception(f"Error in QAO test approval view for IMP RMTR {imp_rmtr_no}: {str(e)}")
        messages.error(request, 'An unexpected error occurred. Please try again.')
        return redirect('imp_pending')
    


    
@login_required
def imp_rmtr_tests_legacy_flat(request, imp_rmtr_no):
    try:
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)
        
        # Collect all test fields from the report
        test_data = {}
        for i in range(1, 17):
            test_carried_out = getattr(report, f'tests_carried_out{i}', '')
            if test_carried_out:
                test_data.update({
                    f'tests_carried_out{i}': test_carried_out,
                    f'sample_results{i}': getattr(report, f'sample_results{i}', ''),
                    f'raw_material_results{i}': getattr(report, f'raw_material_results{i}', ''),
                    f'kapa_standards{i}': getattr(report, f'kapa_standards{i}', '')
                })
        
        return JsonResponse(test_data)
        
    except Exception as e:
        logger.error(f"Error fetching test details for IMP RMTR {imp_rmtr_no}: {str(e)}")
        return JsonResponse({'error': 'Failed to fetch test details'}, status=500)
    


@login_required
def imp_hod_test_approval(request, imp_rmtr_no):
    try:
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)
        
        # Check permissions
        if not request.user.groups.filter(name__in=['HOD', 'HOD_TEST', 'ADMIN']).exists():
            messages.error(request, 'You do not have permission to access this page')
            return redirect('pending')

        if request.method == 'POST':
            # Handle image upload if present
            if 'test_image' in request.FILES:
                try:
                    # Delete old image if it exists and isn't the default
                    if report.test_image and 'default.jpg' not in report.test_image.name:
                        try:
                            report.test_image.delete(save=False)
                        except Exception as e:
                            logger.warning(f"Failed to delete old image for IMP RMTR {imp_rmtr_no}: {str(e)}")
                    
                    # Save new image
                    report.test_image = request.FILES['test_image']
                    report.save()
                    
                    logger.info(f"Successfully updated test image for IMP RMTR {imp_rmtr_no}")
                    return JsonResponse({
                        'success': True,
                        'message': 'Test image updated successfully',
                        'image_url': report.test_image.url
                    })
                except Exception as img_error:
                    logger.error(f"Error updating test image for IMP RMTR {imp_rmtr_no}: {str(img_error)}")
                    return JsonResponse({
                        'success': False,
                        'message': 'Failed to update test image'
                    }, status=500)

            # Handle approval process
            status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            current_time = timezone.now()

            # Update report status
            if status == 'approved':
                report.hod_test_approved = True
                report.hod_test_rejected = False
                report.status = 'Pending: Management Test Approval'
                report.hod_test_date_approved = current_time
                report.hod_test_date_rejected = None
            else:
                # Modified for rejection to continue process
                report.hod_test_approved = False
                report.hod_test_rejected = True
                # Change status to continue to next stage instead of 'rejected'
                report.status = 'Pending: Management Test Approval'
                report.hod_test_date_approved = None
                report.hod_test_date_rejected = current_time

            report.hod_test_comments = comments
            report.save()

            # Send email notification
            try:
                recipients = [ 'neev@kapa-oil.com', 'peter.busolo@kapa-oil.com','ict@kapa-oil.com']
                if request.user.email:
                    recipients.append(request.user.email)
                
                # Update message status to indicate process continues despite rejection
                message_status = "Approved" if status == "approved" else "Rejected"
                
                subject = f'Imports RMTR {imp_rmtr_no} - HOD {report.plant.name} Test {"Approval" if status == "approved" else "Rejection"}'
                message = f"""
                Imports RMTR Details:
                -------------
                RMTR Number: {imp_rmtr_no}

                Status: {message_status}

                Material Name: {report.material_name}

                Material Type: {report.material_type}

                Supplier: {report.supplier}

                Plant: {report.plant.name if report.plant else 'N/A'}

                HOD Test Comments: {comments}
                
                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                Next Stage: Management Test Approval

                Raw Material Test Report Link: http://10.0.0.7:8020
                """
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=False
                )
                logger.info(f"Email notification sent for IMP RMTR {imp_rmtr_no}")
                
            except Exception as e:
                logger.error(f"Failed to send email for IMP RMTR {imp_rmtr_no}: {str(e)}")
                # Continue execution even if email fails

            # If user has FM_TEST permission, provide redirect URL
            if request.user.groups.filter(name='FM_TEST').exists():
                return JsonResponse({
                    'success': True,
                    'message': 'Request processed successfully. Process will continue to next approver.',
                    'status': report.status,
                    'redirect_url': f'/imp_fm_test_approval/{imp_rmtr_no}/'
                })
            
            return JsonResponse({
                'success': True,
                'message': f'Request {status} successfully. Process will continue to Management Test Approval.',
                'status': report.status,
                'redirect_url': '/imp_pending/'
            })

        # GET request
        # Collect test data
        test_data = {}
        for i in range(1, 17):
            test_carried_out = getattr(report, f'tests_carried_out{i}', '')
            if test_carried_out:
                test_data[f'test_{i}'] = {
                    'tests_carried_out': test_carried_out,
                    'sample_results': getattr(report, f'sample_results{i}', ''),
                    'raw_material_results': getattr(report, f'raw_material_results{i}', ''),
                    'kapa_standards': getattr(report, f'kapa_standards{i}', '')
                }

        context = {
            'report': report,
            'page_title': 'IMP HOD Test Approval',
            'can_approve': not report.hod_test_approved,
            'can_reject': not report.hod_test_rejected,
            'user_groups': ','.join(request.user.groups.values_list('name', flat=True)),
            'test_data': test_data  # Added test data to context
        }
        return render(request, 'imp_hod_test_approval.html', context)

    except Exception as e:
        logger.error(f"Error in imp_hod_test_approval: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'POST':
            return JsonResponse({
                'success': False,
                'message': 'An error occurred while processing your request'
            }, status=500)
        else:
            messages.error(request, 'An error occurred while processing your request')
            return redirect('imp_pending')





logger = logging.getLogger(__name__)

@login_required
def imp_rmtr_tests(request, imp_rmtr_no):
    """Return structured test and comment information for a given IMP RMTR."""
    try:
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)

        tests_to_be_done = getattr(report, 'tests', '') or ''

        # Build tests list from individual fields (IMP model mirrors RMTR fields)
        tests_list = []
        for i in range(1, 17):
            entry = {
                'test_number': i,
                'tests_carried_out': getattr(report, f'tests_carried_out{i}', ''),
                'sample_results': getattr(report, f'sample_results{i}', ''),
                'raw_material_results': getattr(report, f'raw_material_results{i}', ''),
                'kapa_standards': getattr(report, f'kapa_standards{i}', '')
            }
            if any(v for k, v in entry.items() if k != 'test_number'):
                tests_list.append(entry)

        # retests
        retests = []
        if hasattr(report, 'imp_rmtr_retests'):
            for r in report.imp_rmtr_retests.all().order_by('-requested_at'):
                retests.append({
                    'requested_at': r.requested_at.isoformat() if r.requested_at else None,
                    'requested_by': r.requested_by.get_full_name() if r.requested_by else None,
                    'reason': r.reason,
                    'comments': r.comments,
                    'completed': bool(r.completed),
                    'test_data': r.test_data or {}
                })

        stage_comments = {
            'lab_qc_comments': getattr(report, 'lab_qc_comments', '') or '',
            'qao_comments': getattr(report, 'qao_comments', '') or '',
            'hod_test_comments': getattr(report, 'hod_test_comments', '') or '',
            'fm_test_comments': getattr(report, 'fm_test_comments', '') or '',
            'management_test_comments': getattr(report, 'management_test_comments', '') or '',
            'milan_comments': getattr(report, 'milan_comments', '') or ''
        }

        logs = []
        if hasattr(report, 'approval_logs'):
            for al in report.approval_logs.all().order_by('-created_at'):
                logs.append({
                    'action': al.action,
                    'comments': al.comments,
                    'retest_reason': getattr(al, 'retest_reason', '') or '',
                    'status': getattr(al, 'status', '') or '',
                    'created_at': al.created_at.isoformat() if al.created_at else None,
                    'user': al.user.get_full_name() if al.user else None
                })

        payload = {
            'tests_to_be_done': tests_to_be_done,
            'tests_list': tests_list,
            'retests': retests,
            'stage_comments': stage_comments,
            'approval_logs': logs
        }

        return JsonResponse(payload)

    except Exception as e:
        logger.error(f"Error fetching test details for IMP RMTR {imp_rmtr_no}: {str(e)}")
        return JsonResponse({'error': 'Failed to fetch test details'}, status=500)


# duplicate simplistic handler removed; structured imp_rmtr_tests above is used

@login_required
def imp_fm_test_approval(request, imp_rmtr_no):
    try:
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)
        
        # Check permissions
        if not request.user.groups.filter(name__in=['FM','FM_TEST','ADMIN']).exists():
            messages.error(request, 'You do not have permission to access this page')
            return redirect('imp_pending')

        if request.method == 'POST':
            if 'test_image' in request.FILES:
                try:
                    if report.test_image and 'default.jpg' not in report.test_image.name:
                        try:
                            report.test_image.delete(save=False)
                        except Exception as e:
                            logger.warning(f"Failed to delete old image for IMP RMTR {imp_rmtr_no}: {str(e)}")
                    
                    report.test_image = request.FILES['test_image']
                    report.save()
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Test image updated successfully',
                        'image_url': report.test_image.url
                    })
                except Exception as e:
                    logger.error(f"Error updating test image: {str(e)}")
                    return JsonResponse({
                        'success': False,
                        'message': 'Failed to update test image'
                    }, status=500)

            status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            current_time = timezone.now()

            if status not in ['approved', 'rejected']:
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid approval status'
                }, status=400)

            if status == 'approved':
                report.fm_test_approved = True
                report.fm_test_rejected = False
                report.status = 'Pending: Management Test Approval'
                report.fm_test_date_approved = current_time
                report.fm_test_date_rejected = None
            else:
                report.fm_test_approved = False
                report.fm_test_rejected = True
                report.status = 'rejected'
                report.fm_test_date_approved = None
                report.fm_test_date_rejected = current_time

            report.fm_test_comments = comments
            report.save()

            try:
                recipients = [
                    'ict@kapa-oil.com',
                    'jaivin@kapa-oil.com', 
                    'neev@kapa-oil.com',
                    request.user.email,
                ]

                subject = f'IMP RMTR {imp_rmtr_no} - FM Test {"Approval" if status == "approved" else "Rejection"}'
                message = f"""
                IMP RMTR Details:
                -------------
                IMP RMTR Number: {imp_rmtr_no}

                Status: {status.title()}

                Material Type: {report.material_type}

                Supplier: {report.supplier}
                
                FM Test Comments: {comments}  
                
                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}
                 Raw Material Test Report Link: http://10.0.0.7:8020
                """
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=False
                )

            except Exception as e:
                logger.error(f"Failed to send email for IMP RMTR {imp_rmtr_no}: {str(e)}")

            return JsonResponse({
                'success': True,
                'message': f'Request {status} successfully',
                'redirect_url': '/imp_pending/'
            })

        # GET request
        context = {
            'report': report,
            'page_title': 'IMP FM Test Approval',
            'can_approve': not report.fm_test_approved,
            'can_reject': not report.fm_test_rejected,
            'test_data': {}, # Test data will be loaded via AJAX
            'imp_rmtr_no': imp_rmtr_no
        }
        return render(request, 'imp_fm_test_approval.html', context)

    except Exception as e:
        logger.error(f"Error in imp_fm_test_approval: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'An error occurred while processing your request'
        }, status=500)
        
logger = logging.getLogger(__name__)

@login_required
def imp_rmtr_tests_legacy_flat2(request, imp_rmtr_no):
    """Dedicated endpoint for fetching test details"""
    try:
        logger.info(f"Fetching test details for IMP RMTR {imp_rmtr_no}")
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)
        
        test_data = {}
        for i in range(1, 17):
            test_carried_out = getattr(report, f'tests_carried_out{i}', '')
            if test_carried_out:
                test_data.update({
                    f'tests_carried_out{i}': test_carried_out,
                    f'sample_results{i}': getattr(report, f'sample_results{i}', ''),
                    f'raw_material_results{i}': getattr(report, f'raw_material_results{i}', ''),
                    f'kapa_standards{i}': getattr(report, f'kapa_standards{i}', '')
                })
        
        return JsonResponse(test_data)
        
    except Exception as e:
        logger.error(f"Error fetching test details for IMP RMTR {imp_rmtr_no}: {str(e)}")
        return JsonResponse({'error': 'Failed to fetch test details'}, status=500)
"""
@login_required
def imp_management_test_approval(request, imp_rmtr_no):
    try:
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)
        
        # Check permissions
        if not request.user.groups.filter(name__in=['MANAGEMENT', 'MANAGEMENT_TEST', 'ADMIN']).exists():
            messages.error(request, 'You do not have permission to access this page')
            return redirect('imp_pending')
        
        if request.method == 'POST':
            if 'test_image' in request.FILES:
                try:
                    if report.test_image and 'default.jpg' not in report.test_image.name:
                        try:
                            report.test_image.delete(save=False)
                        except Exception as e:
                            logger.warning(f"Failed to delete old image for IMP RMTR {imp_rmtr_no}: {str(e)}")
                    
                    report.test_image = request.FILES['test_image']
                    report.save()
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Test image updated successfully',
                        'image_url': report.test_image.url
                    })
                except Exception as e:
                    logger.error(f"Error updating test image: {str(e)}")
                    return JsonResponse({
                        'success': False,
                        'message': 'Failed to update test image'
                    }, status=500)

            status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            current_time = timezone.now()
            
            if status == 'approved':
                report.management_test_approved = True
                report.management_test_rejected = False
                report.status = 'completed'
                report.management_test_date_approved = current_time
                report.management_test_date_rejected = None
            else:
                report.management_test_approved = False
                report.management_test_rejected = True
                report.status = 'rejected'
                report.management_test_date_approved = None
                report.management_test_date_rejected = current_time
            
            report.management_test_comments = comments
            report.save()
            
            # Send email notification
            try:
                recipients = [ request.user.email, 'peter.busolo@kapa-oil.com', 'imports.user3@kapa-oil.com','qao.user6@kapa-oil.com',
                'qao.user1@kapa-oil','ict@kapa-oil.com',]
                
                subject = f'Imports RMTR {imp_rmtr_no} - Management Test {"Approval" if status == "approved" else "Rejection"}'
                message = f'''
                Imports RMTR Details:
                -------------
                RMTR Number: {imp_rmtr_no}
                Status: {status.title()}

                Material Name: {report.material_name}
                Material Type: {report.material_type}
                Supplier: {report.supplier}
                Plant: {report.plant.name if report.plant else 'N/A'}
                Management Test Comments: {comments}
                
                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                Raw Material Test Report Link: http://10.0.0.7:8020
                '''
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=False
                )
                logger.info(f"Email notification sent for IMP RMTR {imp_rmtr_no}")
                
            except Exception as e:
                logger.error(f"Failed to send email for IMP RMTR {imp_rmtr_no}: {str(e)}")
            
            return JsonResponse({
                'success': True,
                'message': f'Request {status} successfully',
                'status': report.status,
                'redirect_url': '/imp_pending/'
            })
        
        # GET request
        test_data = {}
        for i in range(1, 17):
            test_carried_out = getattr(report, f'tests_carried_out{i}', '')
            if test_carried_out:
                test_data.update({
                    f'tests_carried_out{i}': test_carried_out,
                    f'sample_results{i}': getattr(report, f'sample_results{i}', ''),
                    f'raw_material_results{i}': getattr(report, f'raw_material_results{i}', ''),
                    f'kapa_standards{i}': getattr(report, f'kapa_standards{i}', '')
                })

        context = {
            'report': report,
            'page_title': 'IMP Management Test Approval',
            'can_approve': not report.management_test_approved,
            'can_reject': not report.management_test_rejected,
            'user_groups': ','.join(request.user.groups.values_list('name', flat=True)),
            'test_data': test_data,
            'imp_rmtr_no': imp_rmtr_no
        }
        return render(request, 'imp_management_test_approval.html', context)
        
    except Exception as e:
        logger.error(f"Error in imp_management_test_approval: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'POST':
            return JsonResponse({
                'success': False,
                'message': 'An error occurred while processing your request'
            }, status=500)
        else:
            messages.error(request, 'An error occurred while processing your request')
            return redirect('imp_pending')

"""
@login_required
def imp_management_test_approval(request, imp_rmtr_no):
    try:
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)
        
        # Check permissions
        if not request.user.groups.filter(name__in=['MANAGEMENT', 'MANAGEMENT_TEST', 'ADMIN']).exists():
            messages.error(request, 'You do not have permission to access this page')
            return redirect('imp_pending')
        
        if request.method == 'POST':
            if 'test_image' in request.FILES:
                try:
                    if report.test_image and 'default.jpg' not in report.test_image.name:
                        try:
                            report.test_image.delete(save=False)
                        except Exception as e:
                            logger.warning(f"Failed to delete old image for IMP RMTR {imp_rmtr_no}: {str(e)}")
                    
                    report.test_image = request.FILES['test_image']
                    report.save()
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Test image updated successfully',
                        'image_url': report.test_image.url
                    })
                except Exception as e:
                    logger.error(f"Error updating test image: {str(e)}")
                    return JsonResponse({
                        'success': False,
                        'message': 'Failed to update test image'
                    }, status=500)

            status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            current_time = timezone.now()
            
                      
            if status == 'approved':
                report.management_test_approved = True
                report.management_test_rejected = False
                report.status = 'completed'
                report.management_test_date_approved = current_time
                report.management_test_date_rejected = None
            else:
                report.management_test_approved = False
                report.management_test_rejected = True
                report.status = 'rejected'
                report.management_test_date_approved = None
                report.management_test_date_rejected = current_time
            
            report.management_test_comments = comments
            report.save()
            
            #email
            try:
                # Base recipients list
                recipients = [
                    request.user.email,
                    'peter.busolo@kapa-oil.com',
                    'imports.user3@kapa-oil.com',
                    'qao.user6@kapa-oil.com',
                    'qao.user47@kapa-oil.com',
                    'ict@kapa-oil.com',
                ]

                # Plant-specific recipients
                if report.plant:
                    try:
                        # emails (HOD and deputy HOD)
                        plant_emails = report.plant.get_notification_emails()
                        
                        
                        if hasattr(report.plant, 'hod_email') and report.plant.hod_email:
                            recipients.append(report.plant.hod_email)
                        if hasattr(report.plant, 'deputy_hod_email') and report.plant.deputy_hod_email:
                            recipients.append(report.plant.deputy_hod_email)
                            
                        # Add other plant notification emails
                        recipients.extend(plant_emails)
                        
                        logger.info(f"Added plant-specific recipients for plant {report.plant.name}")
                    except Exception as e:
                        logger.error(f"Error getting plant-specific recipients for plant {report.plant.name}: {str(e)}")
                
                # Remove duplicates while preserving order
                recipients = list(dict.fromkeys(filter(None, recipients)))
                
                subject = f'Imports RMTR {imp_rmtr_no} - Management Test {"Approval" if status == "approved" else "Rejection"}'
                message = f"""
                Imports RMTR Details:
                -------------
                RMTR Number: {imp_rmtr_no}

                Status: {status.title()}

                Material Name: {report.material_name}

                Material Type: {report.material_type}

                Supplier: {report.supplier}
                
                Plant: {report.plant.name if report.plant else 'N/A'}

                Management Test Comments: {comments}
                
                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                Raw Material Test Report Link: http://10.0.0.7:8020
                """
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=False
                )
                logger.info(f"Email notification sent for IMP RMTR {imp_rmtr_no} to recipients: {recipients}")
                
            except Exception as e:
                logger.error(f"Failed to send email for IMP RMTR {imp_rmtr_no}: {str(e)}")
            
            return JsonResponse({
                'success': True,
                'message': f'Request {status} successfully',
                'status': report.status,
                'redirect_url': '/imp_pending/'
            })
        
        # GET request
        test_data = {}
        for i in range(1, 17):
            test_carried_out = getattr(report, f'tests_carried_out{i}', '')
            if test_carried_out:
                test_data.update({
                    f'tests_carried_out{i}': test_carried_out,
                    f'sample_results{i}': getattr(report, f'sample_results{i}', ''),
                    f'raw_material_results{i}': getattr(report, f'raw_material_results{i}', ''),
                    f'kapa_standards{i}': getattr(report, f'kapa_standards{i}', '')
                })

        context = {
            'report': report,
            'page_title': 'IMP Management Test Approval',
            'can_approve': not report.management_test_approved,
            'can_reject': not report.management_test_rejected,
            'user_groups': ','.join(request.user.groups.values_list('name', flat=True)),
            'test_data': test_data,
            'imp_rmtr_no': imp_rmtr_no
        }
        return render(request, 'imp_management_test_approval.html', context)
        
    except Exception as e:
        logger.error(f"Error in imp_management_test_approval: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'POST':
            return JsonResponse({
                'success': False,
                'message': 'An error occurred while processing your request'
            }, status=500)
        else:
            messages.error(request, 'An error occurred while processing your request')
            return redirect('imp_pending')


            

@login_required
def imp_milan_approval(request, imp_rmtr_no):
    """
    Handle Milan approval process for IMP RMTR requests.
    Allows authorized users to approve or reject requests and sends email notifications.
    """
    try:
        logger.info(f"Accessing imp_milan_approval for IMP RMTR {imp_rmtr_no}")
        report = get_object_or_404(IMP_RMTRRequest, imp_rmtr_no=imp_rmtr_no)
        
        # Check user permissions
        user_groups = list(request.user.groups.values_list('name', flat=True))
        logger.info(f"User {request.user.username} groups: {user_groups}")
        
        if not request.user.groups.filter(name__in=['MILAN', 'ADMIN']).exists():
            logger.warning(f"User {request.user.username} denied access - insufficient permissions")
            messages.error(request, 'You do not have permission to access this page')
            return redirect('imp_pending')
            
      
        if request.method == 'POST':
            if 'test_image' in request.FILES:
                try:
                    if report.test_image and 'default.jpg' not in report.test_image.name:
                        try:
                            report.test_image.delete(save=False)
                        except Exception as e:
                            logger.warning(f"Failed to delete old image for IMP RMTR {imp_rmtr_no}: {str(e)}")
                    
                    report.test_image = request.FILES['test_image']
                    report.save()
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Test image updated successfully',
                        'image_url': report.test_image.url
                    })
                except Exception as e:
                    logger.error(f"Error updating test image: {str(e)}")
                    return JsonResponse({
                        'success': False,
                        'message': 'Failed to update test image'
                    }, status=500)

            status = request.POST.get('approval_status')
            comments = request.POST.get('comments')
            current_time = timezone.now()
            
            # Validate status
            if status not in ['approved', 'rejected']:
                logger.error(f"Invalid approval status received: {status}")
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid approval status'
                }, status=400)
            
            # Update report status and fields
            if status == 'approved':
                report.milan_approved = True
                report.milan_rejected = False
                report.status = 'completed'
                report.milan_date_approved = current_time
                report.milan_date_rejected = None
            else:  # rejected
                report.milan_approved = False
                report.milan_rejected = True
                report.status = 'rejected'
                report.milan_date_approved = None
                report.milan_date_rejected = current_time
            
            report.milan_comments = comments
            report.save()
            
            # Send email notification
            try:
                recipients = ['ict@kapa-oil.com',
                'purchase.user1@kapa-oil.com',
                'neev@kapa-oil.com',
                'jaivin@kapa-oil.com',
                'fm@kapa-oil.com',
                'kishore@kapa-oil.com',
                'qao.user6@kapa-oil.com',
                'qao.user5@kapa-oil',
                request.user.email
                ]
                
                subject = f'IMP RMTR {imp_rmtr_no} - Milan {"Approval" if status == "approved" else "Rejection"}'
                message = f"""
                IMP RMTR Details:
                -------------
                IMP RMTR Number: {imp_rmtr_no}

                Status: {status.title()}

                Material: {report.material_type}

                Supplier: {report.supplier}
                
                Milan Comments: {comments}
                
                Action By: {request.user.get_full_name() or request.user.username}
                Date: {current_time.strftime("%Y-%m-%d %H:%M:%S")}

                 Raw Material Test Report Link: http://10.0.0.7:8020
                """
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='kapaportal@kapa-oil.local',
                    recipient_list=recipients,
                    fail_silently=False
                )
                logger.info(f"Email notification sent for IMP RMTR {imp_rmtr_no}")
                
            except Exception as e:
                logger.error(f"Failed to send email for IMP RMTR {imp_rmtr_no}: {str(e)}")
                # Continue execution even if email fails
            
            return JsonResponse({
                'success': True,
                'message': f'Request {status} successfully'
            })

        # GET request
        test_data = {}
        for i in range(1, 17):
            test_carried_out = getattr(report, f'tests_carried_out{i}', '')
            if test_carried_out:
                test_data.update({
                    f'tests_carried_out{i}': test_carried_out,
                    f'sample_results{i}': getattr(report, f'sample_results{i}', ''),
                    f'raw_material_results{i}': getattr(report, f'raw_material_results{i}', ''),
                    f'kapa_standards{i}': getattr(report, f'kapa_standards{i}', '')
                })

        context = {
            'report': report,
            'page_title': 'IMP Milan Approval',
            'can_approve': not report.milan_approved,
            'can_reject': not report.milan_rejected,
            'user_groups': ','.join(user_groups),
            'test_data': test_data,
            'imp_rmtr_no': imp_rmtr_no
        }
        return render(request, 'imp_milan_approval.html', context)

    except Exception as e:
        logger.exception(f"Error in imp_milan_approval view for IMP RMTR {imp_rmtr_no}: {str(e)}")
        messages.error(request, 'An error occurred while processing your request')
        return redirect('imp_pending')
    
    





@login_required
def imp_completed_reports(request):
    """View for completed IMP RMTR reports with filtering and export capabilities"""
    try:
        # Get filter parameters
        date_from = request.GET.get('date_from', (timezone.now() - timedelta(days=365)).date())
        date_to = request.GET.get('date_to', timezone.now().date())
        material_type = request.GET.get('material_type')
        search_query = request.GET.get('search')
        export_format = request.GET.get('export')

        # Base query for completed reports - including both completed and completed-rejected status
        completed_rmtrs = IMP_RMTRRequest.objects.filter(
            Q(status__iexact='completed') | 
            Q(status__iexact='rejected')
        ).select_related(
            'supplier',
            'plant'
        ).order_by('-date_created', '-imp_rmtr_no')

        # Apply filters
        if date_from:
            completed_rmtrs = completed_rmtrs.filter(date_created__date__gte=date_from)
        if date_to:
            completed_rmtrs = completed_rmtrs.filter(date_created__date__lte=date_to)
        if material_type:
            completed_rmtrs = completed_rmtrs.filter(material_type=material_type)
        if search_query:
            completed_rmtrs = completed_rmtrs.filter(
                Q(imp_rmtr_no__icontains=search_query) |
                Q(material_type__icontains=search_query) |
                Q(sub_category__icontains=search_query) |
                Q(supplier__name__icontains=search_query)
            )

        # Handle exports
        if export_format == 'excel':
            try:
                return imp_export_to_excel(completed_rmtrs)
            except Exception as e:
                logger.error(f"Excel export error: {str(e)}")
                messages.error(request, 'Error exporting to Excel')
                return redirect('imp_completed_reports')

        # Render all rows so client-side search covers every report
        page_obj = list(completed_rmtrs)

        # Get distinct material types from both completed and completed-rejected reports
        material_types = IMP_RMTRRequest.objects.filter(
            Q(status__iexact='completed') | 
            Q(status__iexact='rejected')
        ).values_list('material_type', flat=True).distinct()

        context = {
            'completed_reports': page_obj,
            'material_types': material_types,
            'filters': {
                'date_from': date_from,
                'date_to': date_to,
                'material_type': material_type,
                'search': search_query
            },
            'total_reports': completed_rmtrs.count(),
        }

        return render(request, 'imp_completed_reports.html', context)

    except Exception as e:
        logger.error(f"Error in imp_completed_reports view: {str(e)}")
        messages.error(request, 'Error loading completed IMP reports')
        return redirect('dashboard')
    


@login_required
def imp_get_rmtr_tests(request, imp_rmtr_no):
    """API endpoint for getting test details"""
    try:
        report = IMP_RMTRRequest.objects.get(imp_rmtr_no=imp_rmtr_no)
        
        test_data = {}
        for i in range(1, 17):
            if getattr(report, f'tests_carried_out{i}'):
                test_data[f'tests_carried_out{i}'] = getattr(report, f'tests_carried_out{i}')
                test_data[f'sample_results{i}'] = getattr(report, f'sample_results{i}')
                test_data[f'raw_material_results{i}'] = getattr(report, f'raw_material_results{i}')
                test_data[f'kapa_standards{i}'] = getattr(report, f'kapa_standards{i}')
        
        return JsonResponse(test_data)
        
    except IMP_RMTRRequest.DoesNotExist:
        return JsonResponse({'error': f'IMP RMTR {imp_rmtr_no} not found'}, status=404)
    except Exception as e:
        logger.error(f"Error getting IMP RMTR tests: {str(e)}")
        return JsonResponse({'error': 'Server error'}, status=500)


def imp_export_to_excel(queryset):
    """Export completed IMP reports to Excel with all fields"""
    try:
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'remove_timezone': True})
        worksheet = workbook.add_worksheet('Completed IMP RMTRs')

        # Styles
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#3A6D8C',
            'color': 'white',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True
        })

        cell_format = workbook.add_format({
            'border': 1,
            'align': 'left',
            'valign': 'vcenter',
            'text_wrap': True
        })

        date_format = workbook.add_format({
            'border': 1,
            'align': 'left',
            'valign': 'vcenter',
            'num_format': 'dd/mm/yyyy'
        })

        # Set column widths (adjusted for all columns)
        worksheet.set_column('A:A', 15)   # IMP RMTR No
        worksheet.set_column('B:B', 12)   # Date Created
        worksheet.set_column('C:C', 25)   # Supplier
        worksheet.set_column('D:D', 20)   # Material Name
        worksheet.set_column('E:E', 15)   # Plant
        worksheet.set_column('F:F', 30)   # Justification
        worksheet.set_column('G:G', 30)   # Specs
        worksheet.set_column('H:H', 12)   # Status
        worksheet.set_column('I:I', 20)   # Material Type
        worksheet.set_column('J:J', 20)   # Sub Category
        worksheet.set_column('K:K', 30)   # Tests Carried Out
        worksheet.set_column('L:L', 30)   # Raw Material Results
        worksheet.set_column('M:M', 30)   # KAPA Standards
        worksheet.set_column('N:N', 30)   # Sample Results
        worksheet.set_column('O:O', 20)   # Requested By
        worksheet.set_column('P:P', 12)   # Quantity
        worksheet.set_column('Q:Q', 12)   # UOM
        worksheet.set_column('R:R', 30)   # Lab QC Comments
        worksheet.set_column('S:S', 30)   # QAO Comments
        worksheet.set_column('T:T', 30)   # HOD Test Comments
        worksheet.set_column('U:U', 30)   # FM Test Comments
        #worksheet.set_column('V:V', 30)   # Management Test Comments
        #worksheet.set_column('W:W', 30)   # Milan Comments

        # Define all headers matching the HTML checkboxes order
        headers = [
            'IMP RMTR No',                  # 0
            'Date Created',                 # 1
            'Supplier',                     # 2
            'Material Name',                # 3
            'Plant',                        # 4
            'Justification',                # 5
            'Specs',                        # 6
            'Status',                       # 7
            'Material Type',                # 8
            'Sub Category',                 # 9
            'Tests Carried Out',            # 10
            'Raw Material Results',         # 11
            'KAPA Standards',               # 12
            'Sample Results',               # 13
            'Requested By',                 # 14
            'Quantity',                     # 15
            'UOM',                          # 16
            'Lab QC Comments',              # 17
            'QAO Comments',                 # 18
            'HOD Test Comments',            # 19
            'Management Test Comments',             # 20
            'Management Test Comments',     # 21
            'Milan Comments'                # 22
        ]

        # Write headers
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)

        # Write data
        for row, report in enumerate(queryset, start=1):
            col = 0
            
            # IMP RMTR No
            worksheet.write(row, col, report.imp_rmtr_no, cell_format)
            col += 1
            
            # Date Created
            local_date = report.date_created.astimezone().replace(tzinfo=None)
            worksheet.write(row, col, local_date, date_format)
            col += 1
            
            # Supplier
            worksheet.write(row, col, report.supplier.name if report.supplier else 'N/A', cell_format)
            col += 1
            
            # Material Name
            worksheet.write(row, col, getattr(report, 'material_name', 'N/A'), cell_format)
            col += 1
            
            # Plant
            worksheet.write(row, col, report.plant.name if report.plant else 'N/A', cell_format)
            col += 1
            
            # Justification
            worksheet.write(row, col, getattr(report, 'justification', ''), cell_format)
            col += 1
            
            # Specs
            worksheet.write(row, col, getattr(report, 'specs', ''), cell_format)
            col += 1
            
            # Status
            worksheet.write(row, col, report.status.title(), cell_format)
            col += 1
            
            # Material Type
            worksheet.write(row, col, report.material_type, cell_format)
            col += 1
            
            # Sub Category
            worksheet.write(row, col, report.sub_category, cell_format)
            col += 1

            # Combine all test results for this report
            all_tests = []
            all_raw_results = []
            all_kapa_standards = []
            all_sample_results = []

            # Loop through test fields 1-16
            for i in range(1, 17):
                tests_carried = getattr(report, f'tests_carried_out{i}', '')
                if tests_carried:
                    all_tests.append(tests_carried)
                    all_raw_results.append(getattr(report, f'raw_material_results{i}', ''))
                    all_kapa_standards.append(getattr(report, f'kapa_standards{i}', ''))
                    all_sample_results.append(getattr(report, f'sample_results{i}', ''))

            # Tests Carried Out
            worksheet.write(row, col, '\n'.join(filter(None, all_tests)), cell_format)
            col += 1
            
            # Raw Material Results
            worksheet.write(row, col, '\n'.join(filter(None, all_raw_results)), cell_format)
            col += 1
            
            # KAPA Standards
            worksheet.write(row, col, '\n'.join(filter(None, all_kapa_standards)), cell_format)
            col += 1
            
            # Sample Results
            worksheet.write(row, col, '\n'.join(filter(None, all_sample_results)), cell_format)
            col += 1
            
            # Requested By
            worksheet.write(row, col, getattr(report, 'requested_by', ''), cell_format)
            col += 1
            
            # Quantity
            worksheet.write(row, col, str(getattr(report, 'quantity', '')), cell_format)
            col += 1
            
            # UOM
            worksheet.write(row, col, getattr(report, 'uom', ''), cell_format)
            col += 1
            
            # Lab QC Comments
            worksheet.write(row, col, getattr(report, 'lab_qc_comments', ''), cell_format)
            col += 1
            
            # QAO Comments
            worksheet.write(row, col, getattr(report, 'qao_comments', ''), cell_format)
            col += 1
            
            # HOD Test Comments
            worksheet.write(row, col, getattr(report, 'hod_test_comments', ''), cell_format)
            col += 1
            
            # FM Test Comments
            #worksheet.write(row, col, getattr(report, 'fm_test_comments', ''), cell_format)
            #col += 1
            
            # Management Test Comments
            worksheet.write(row, col, getattr(report, 'management_test_comments', ''), cell_format)
            col += 1
            
            # Milan Comments
            #worksheet.write(row, col, getattr(report, 'milan_comments', ''), cell_format)

        # Add autofilter
        worksheet.autofilter(0, 0, queryset.count(), len(headers) - 1)

        # Close the workbook
        workbook.close()

        # Create response
        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="IMP_RMTRs_{timezone.now().strftime("%Y%m%d")}.xlsx"'
        return response

    except Exception as e:
        logger.error(f"Error exporting IMP to Excel: {str(e)}")
        raise

@login_required
def imp_download_rmtr_pdf(request, imp_rmtr_no):
    """
    Generate and return PDF for IMP RMTR report.
    Supports both preview (inline) and download (attachment) modes.
    """
    try:
        # Get the report with related data
        report = IMP_RMTRRequest.objects.select_related(
            'supplier',
            'plant'
        ).get(imp_rmtr_no=imp_rmtr_no)

        # Process test results
        test_results = []
        for i in range(1, 17):
            test = {
                'tests_carried_out': getattr(report, f'tests_carried_out{i}', ''),
                'sample_results': getattr(report, f'sample_results{i}', ''),
                'raw_material_results': getattr(report, f'raw_material_results{i}', ''),
                'kapa_standards': getattr(report, f'kapa_standards{i}', '')
            }
            # Only add tests that have actual content
            if any(value.strip() for value in test.values() if value):
                test_results.append(test)

        # Modified pagination logic - 7 items on first page, 7 on subsequent pages
        first_page_items = 7
        other_pages_items = 7
        total_items = len(test_results)
        
        # Calculate if we need to force a new page for management section
        force_new_page = total_items == 7  # Force new page if exactly 7 items
        
        # Calculate total pages needed
        remaining_items = max(0, total_items - first_page_items)
        additional_pages = (remaining_items + other_pages_items - 1) // other_pages_items
        total_pages = 1 + additional_pages if remaining_items > 0 else 1

        pages_data = []
        
        # First page
        first_page_tests = test_results[:first_page_items]
        pages_data.append({
            'page_num': 0,
            'test_results': first_page_tests,
            'is_first_page': True,
            'is_last_page': total_items <= first_page_items,
            'current_page': 1,
            'total_pages': total_pages,
            'force_new_page': force_new_page
        })

        # Subsequent pages
        remaining_tests = test_results[first_page_items:]
        for page_num in range(1, total_pages):
            start_idx = (page_num - 1) * other_pages_items
            end_idx = min(start_idx + other_pages_items, len(remaining_tests))
            
            page_tests = remaining_tests[start_idx:end_idx]
            
            pages_data.append({
                'page_num': page_num,
                'test_results': page_tests,
                'is_first_page': False,
                'is_last_page': page_num == total_pages - 1,
                'current_page': page_num + 1,
                'total_pages': total_pages,
                'force_new_page': force_new_page and page_num == total_pages - 1
            })

        # Use absolute paths for better reliability
        base_dir = Path(__file__).resolve().parent.parent
        static_dir = base_dir / 'static' / 'images'
        letterhead_path = static_dir / 'Letterhead.png'

        if not letterhead_path.exists():
            logger.error(f"Letterhead image not found at: {letterhead_path}")
            messages.error(request, 'Letterhead image not found')
            return redirect('imp_completed_reports')

        try:
            with open(str(letterhead_path), 'rb') as img_file:
                letterhead_base64 = base64.b64encode(img_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to encode letterhead image: {str(e)}")
            messages.error(request, 'Error processing letterhead image')
            return redirect('imp_completed_reports')

        context = {
            'report': report,
            'pages_data': pages_data,
            'generated_date': timezone.now(),
            'title': 'IMPORTED RAW MATERIAL TEST REPORT',
            'letterhead_base64': letterhead_base64,
            'total_pages': total_pages,
            'total_items': total_items
        }

        template = get_template('pdf/imp_rmtr_report_pdf.html')
        html_content = template.render(context)

        # PDF generation options
        options = {
            'page-size': 'A4',
            'margin-top': '0',
            'margin-right': '0',
            'margin-bottom': '0',
            'margin-left': '0',
            'encoding': 'UTF-8',
            'enable-local-file-access': None,
            'quiet': None,
            'print-media-type': None,
            'zoom': 1.0,
            'dpi': 300,
            'orientation': 'Portrait',
            'background': True,
            'no-outline': None,
            'disable-smart-shrinking': True
        }

        # Configure wkhtmltopdf path
        wkhtmltopdf_path = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
        if not os.path.exists(wkhtmltopdf_path):
            # Try alternative paths
            alternative_paths = [
                '/usr/local/bin/wkhtmltopdf',
                '/usr/bin/wkhtmltopdf',
                'wkhtmltopdf'  # System PATH
            ]
            for alt_path in alternative_paths:
                if os.path.exists(alt_path):
                    wkhtmltopdf_path = alt_path
                    break
            else:
                logger.error(f"wkhtmltopdf not found")
                messages.error(request, 'PDF generation tool not found')
                return redirect('imp_completed_reports')

        config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)

        # Generate PDF
        try:
            pdf = pdfkit.from_string(
                html_content, 
                False, 
                options=options, 
                configuration=config
            )
        except Exception as e:
            logger.error(f"PDF generation failed: {str(e)}")
            messages.error(request, 'Error generating PDF document')
            return redirect('imp_completed_reports')

        # Create HTTP response with PDF content
        response = HttpResponse(pdf, content_type='application/pdf')
        
        # Set headers to allow iframe embedding
        response['X-Frame-Options'] = 'SAMEORIGIN'
        response['Content-Security-Policy'] = "frame-ancestors 'self';"
        
        # Determine if this is a preview or download request
        is_preview = request.GET.get('preview', '').lower() == 'true'
        
        # Set appropriate Content-Disposition header
        filename = f"IMP_RMTR_{report.imp_rmtr_no}_{timezone.now().strftime('%Y%m%d')}.pdf"
        if is_preview:
            # inline disposition displays in browser/iframe
            response['Content-Disposition'] = f'inline; filename="{filename}"'
        else:
            # attachment disposition forces download
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Add cache control headers for better performance
        response['Cache-Control'] = 'private, max-age=3600'
        
        return response

    except IMP_RMTRRequest.DoesNotExist:
        logger.error(f"IMP RMTR report not found: {imp_rmtr_no}")
        messages.error(request, 'Report not found')
        return redirect('imp_completed_reports')
    except Exception as e:
        logger.error(f"Unexpected error generating PDF: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        messages.error(request, 'Error generating PDF')
        return redirect('imp_completed_reports')


@login_required
def imp_preview_rmtr_pdf(request, imp_rmtr_no):
    """Preview IMP PDF in browser"""
    try:
        # Get the report with related data
        report = IMP_RMTRRequest.objects.select_related(
            'supplier',
            'plant'
        ).get(imp_rmtr_no=imp_rmtr_no)

        # Process test results
        test_results = []
        for i in range(1, 17):
            test = {
                'tests_carried_out': getattr(report, f'tests_carried_out{i}', ''),
                'sample_results': getattr(report, f'sample_results{i}', ''),
                'raw_material_results': getattr(report, f'raw_material_results{i}', ''),
                'kapa_standards': getattr(report, f'kapa_standards{i}', '')
            }
            # Only add tests that have actual content
            if any(value.strip() for value in test.values() if value):
                test_results.append(test)

        # Modified pagination logic
        first_page_items = 7
        other_pages_items = 7
        total_items = len(test_results)
        
        # Calculate total pages needed
        remaining_items = max(0, total_items - first_page_items)
        additional_pages = (remaining_items + other_pages_items - 1) // other_pages_items if remaining_items > 0 else 0
        total_pages = 1 + additional_pages

        # Pre-process pages data
        pages_data = []
        
        # First page
        first_page_tests = test_results[:first_page_items]
        pages_data.append({
            'page_num': 0,
            'test_results': first_page_tests,
            'is_first_page': True,
            'is_last_page': total_pages == 1,
            'current_page': 1,
            'total_pages': total_pages
        })

        # Subsequent pages
        if total_pages > 1:
            remaining_tests = test_results[first_page_items:]
            for page_num in range(1, total_pages):
                start_idx = (page_num - 1) * other_pages_items
                end_idx = min(start_idx + other_pages_items, len(remaining_tests))
                
                page_tests = remaining_tests[start_idx:end_idx]
                
                pages_data.append({
                    'page_num': page_num,
                    'test_results': page_tests,
                    'is_first_page': False,
                    'is_last_page': page_num == total_pages - 1,
                    'current_page': page_num + 1,
                    'total_pages': total_pages
                })

        # Use absolute paths
        base_dir = Path(__file__).resolve().parent.parent
        static_dir = base_dir / 'static' / 'images'
        letterhead_path = static_dir / 'Letterhead.png'

        if not letterhead_path.exists():
            logger.error(f"Letterhead image not found at: {letterhead_path}")
            messages.error(request, 'Letterhead image not found')
            return redirect('imp_completed_reports')

        try:
            letterhead_base64 = get_base64_encoded_image(letterhead_path)
            if not letterhead_base64:
                raise ValueError("Failed to encode letterhead image")
        except Exception as e:
            logger.error(f"Failed to encode letterhead image: {str(e)}")
            messages.error(request, 'Error processing letterhead image')
            return redirect('imp_completed_reports')

        context = {
            'report': report,
            'pages_data': pages_data,
            'generated_date': timezone.now(),
            'title': 'IMPORTED RAW MATERIAL TEST REPORT',
            'letterhead_base64': letterhead_base64,
            'total_pages': total_pages,
            'total_items': total_items
        }

        template = get_template('pdf/imp_rmtr_report_pdf.html')
        html_content = template.render(context)

        # PDF generation options
        options = {
            'page-size': 'A4',
            'margin-top': '0',
            'margin-right': '0',
            'margin-bottom': '0',
            'margin-left': '0',
            'encoding': 'UTF-8',
            'enable-local-file-access': None,
            'quiet': None,
            'print-media-type': None,
            'zoom': 1.0,
            'dpi': 300,
            'orientation': 'Portrait',
            'background': True,
            'no-outline': None,
            'disable-smart-shrinking': True
        }

        wkhtmltopdf_path = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
        if not os.path.exists(wkhtmltopdf_path):
            logger.error(f"wkhtmltopdf not found at: {wkhtmltopdf_path}")
            messages.error(request, 'PDF generation tool not found')
            return redirect('imp_completed_reports')

        config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)

        try:
            pdf = pdfkit.from_string(
                html_content, 
                False, 
                options=options, 
                configuration=config
            )
        except Exception as e:
            logger.error(f"PDF generation failed: {str(e)}")
            messages.error(request, 'Error generating PDF document')
            return redirect('imp_completed_reports')

        # Create response with proper headers for iframe embedding
        response = HttpResponse(content_type='application/pdf')
        response['X-Frame-Options'] = 'SAMEORIGIN'
        response['Content-Security-Policy'] = "frame-ancestors 'self';"
        response['Content-Disposition'] = f'inline; filename="IMP_RMTR_{report.imp_rmtr_no}_{timezone.now().strftime("%Y%m%d")}.pdf"'
        response.write(pdf)
        
        return response

    except IMP_RMTRRequest.DoesNotExist:
        logger.error(f"IMP RMTR report not found: {imp_rmtr_no}")
        messages.error(request, 'Report not found')
        return redirect('imp_completed_reports')
    except Exception as e:
        logger.error(f"Error previewing PDF for IMP RMTR {imp_rmtr_no}: {str(e)}")
        messages.error(request, 'Error generating PDF preview')
        return redirect('imp_completed_reports')


@login_required
def get_imp_rmtr_tests(request, imp_rmtr_no):
    """Get test data for IMP RMTR (already exists, just included for completeness)"""
    try:
        report = IMP_RMTRRequest.objects.get(imp_rmtr_no=imp_rmtr_no)
        test_data = {}
        for i in range(1, 17):
            test_data[f'tests_carried_out{i}'] = getattr(report, f'tests_carried_out{i}', '') or ''
            test_data[f'sample_results{i}'] = getattr(report, f'sample_results{i}', '') or ''
            test_data[f'raw_material_results{i}'] = getattr(report, f'raw_material_results{i}', '') or ''
            test_data[f'kapa_standards{i}'] = getattr(report, f'kapa_standards{i}', '') or ''
        return JsonResponse(test_data)
    except IMP_RMTRRequest.DoesNotExist:
        return JsonResponse({'error': 'Report not found'}, status=404)
    

class IMPRMTRTestView:
    @staticmethod
    def get_test_data(imp_rmtr_request):
        """Helper method to get all test data from an IMP RMTR request"""
        test_data = []
        
        for i in range(1, 17):  # Model has 16 sets of test fields
            test_entry = {
                'test_number': i,
                'tests_carried_out': getattr(imp_rmtr_request, f'tests_carried_out{i}', ''),
                'sample_results': getattr(imp_rmtr_request, f'sample_results{i}', ''),
                'raw_material_results': getattr(imp_rmtr_request, f'raw_material_results{i}', ''),
                'kapa_standards': getattr(imp_rmtr_request, f'kapa_standards{i}', '')
            }
            
            # Only include entries that have data
            if any(value for key, value in test_entry.items() if key != 'test_number'):
                test_data.append(test_entry)
                
        return test_data

class IMPRMTRDetailView(DetailView):
    model = IMP_RMTRRequest
    template_name = 'imp_completed_reports.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['test_data'] = IMPRMTRTestView.get_test_data(self.object)
        return context

def imp_get_report_data(request, imp_rmtr_no):
    """API endpoint for getting IMP report details"""
    try:
        report = IMP_RMTRRequest.objects.select_related(
            'supplier', 
            'plant'
        ).get(imp_rmtr_no=imp_rmtr_no)

        data = {
            'imp_rmtr_no': report.imp_rmtr_no,
            'date': report.date_created.strftime('%Y-%m-%d'),
            'material_type': report.material_type,
            'sub_category': report.sub_category,
            'supplier': report.supplier.name if report.supplier else 'N/A',
            'plant': report.plant.name if report.plant else 'N/A',
            'tests': report.tests or '',
            'status': report.status,
            'requested_by': report.requested_by,
            'justification': report.justification,
            'uom': report.uom,
            'quantity': report.quantity,
            'specs': report.specs,
        }

        # Add approval information if available
        if hasattr(report, 'management_test_date_approved'):
            data['management_test_date_approved'] = (
                report.management_test_date_approved.strftime('%Y-%m-%d') 
                if report.management_test_date_approved else None
            )

        return JsonResponse(data)

    except IMP_RMTRRequest.DoesNotExist:
        return JsonResponse(
            {'error': 'IMP Report not found'}, 
            status=404
        )
    except Exception as e:
        return JsonResponse(
            {'error': f'Server error: {str(e)}'}, 
            status=500
        )

def imp_process_test_results(report):
    """Process IMP test results into structured format"""
    tests_list = []
    
    # Handle different formats of data storage (comma or newline separated)
    separators = [',', '\n']
    
    def split_field(field):
        if not field:
            return []
        for sep in separators:
            if sep in field:
                return [item.strip() for item in field.split(sep) if item.strip()]
        return [field.strip()]
    
    # Split all fields
    tests = split_field(report.tests)
    raw_material_results = []
    sample_results = []
    kapa_standards = []
    
    # Collect results from all test fields
    for i in range(1, 17):
        if getattr(report, f'tests_carried_out{i}'):
            raw_material_results.append(getattr(report, f'raw_material_results{i}', ''))
            sample_results.append(getattr(report, f'sample_results{i}', ''))
            kapa_standards.append(getattr(report, f'kapa_standards{i}', ''))
    
    # Get the maximum length of all lists
    max_length = max(
        len(tests),
        len(raw_material_results),
        len(sample_results),
        len(kapa_standards)
    )
    
    # Pad shorter lists with N/A
    tests.extend(['N/A'] * (max_length - len(tests)))
    raw_material_results.extend(['N/A'] * (max_length - len(raw_material_results)))
    sample_results.extend(['N/A'] * (max_length - len(sample_results)))
    kapa_standards.extend(['N/A'] * (max_length - len(kapa_standards)))
    
    # Combine all results
    for i in range(max_length):
        tests_list.append({
            'test': tests[i],
            'result': raw_material_results[i],
            'sample': sample_results[i],
            'standard': kapa_standards[i]
        })
    
    return tests_list

def imp_check_rmtr(request, imp_rmtr_no):
    """Debug endpoint to check IMP RMTR existence and details"""
    try:
        rmtrs = list(IMP_RMTRRequest.objects.filter(imp_rmtr_no=imp_rmtr_no).values())
        
        debug_info = {
            'requested_imp_rmtr': imp_rmtr_no,
            'found_rmtrs': rmtrs,
            'total_matching': len(rmtrs),
            'all_rmtrs': list(IMP_RMTRRequest.objects.values_list('imp_rmtr_no', flat=True).order_by('-imp_rmtr_no'))
        }
        
        return JsonResponse(debug_info)
    except Exception as e:
        return JsonResponse({'error': str(e)})

# Register template filters
@register.filter
def multiply(value, arg):
    """Multiply the arg by the value"""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def add(value, arg):
    """Add the arg to the value"""
    try:
        return int(value) + int(arg)
    except (ValueError, TypeError):
        return 0

def get_base64_encoded_image(image_path):
    """Convert image to base64 string"""
    try:
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"Error encoding image {image_path}: {str(e)}")
        return None
    
def imp_get_rmtr_report(request, imp_rmtr_no):
    try:
        rmtr = IMP_RMTRRequest.objects.get(imp_rmtr_no=imp_rmtr_no)
        data = {
            'imp_rmtr_no': rmtr.imp_rmtr_no,
            'material_type': rmtr.material_type,
            'sub_category': rmtr.sub_category,
            'status': rmtr.status,
            'date': rmtr.date.strftime('%Y-%m-%d'),
            'management_test_date_approved': rmtr.management_test_date_approved.strftime('%Y-%m-%d') if rmtr.management_test_date_approved else None,
        }
        return JsonResponse(data)
    except IMP_RMTRRequest.DoesNotExist:
        return JsonResponse({'error': 'RMTR not found'}, status=404)

@login_required
def imp_all_rmtrs(request):
    try:
        user_groups = list(request.user.groups.values_list('name', flat=True))
        logger.info(f"User groups for {request.user.username}: {user_groups}")

        if not user_groups:
            messages.error(request, 'You do not have any assigned roles. Please contact your administrator.')
            return redirect('login')

        # Get ALL IMP requests without excluding any status
        reports = IMP_RMTRRequest.objects.all()

        # Apply search if provided
        search_query = request.GET.get('search')
        if search_query:
            reports = reports.filter(
                Q(imp_rmtr_no__icontains=search_query) |
                Q(supplier__name__icontains=search_query) |
                Q(material_type__icontains=search_query) |
                Q(plant__name__icontains=search_query)
            )

        # Apply sorting
        sort_field = request.GET.get('sort', '-date_created')
        reports = reports.order_by(sort_field)

        # Process each report for display
        for report in reports:
            normalized_status = normalize_status(report.status)
            report.internal_status = normalized_status
            
            # Set display status using the mapping
            config = STATUS_CONFIG.get(normalized_status, {})
            report.display_status = config.get('display', report.status)
            
            # Add retest capabilities
            report.can_retest = config.get('can_retest', False)
            if report.can_retest:
                report.retest_chain = config.get('retest_chain', [])
                report.user_can_retest = any(group in report.retest_chain for group in user_groups)
            else:
                report.user_can_retest = False

        # Render all rows so client-side search covers every report
        reports = list(reports)

        context = {
            'pending_reports': reports,
            'user_groups': user_groups,
            'search_query': search_query,
            'current_sort': sort_field,
            'status_config': STATUS_CONFIG,
            'status_display_mapping': STATUS_DISPLAY_MAPPING
        }

        return render(request, 'imp_all_rmtrs.html', context)

    except Exception as e:
        logger.exception(f"Error in imp_pending_view: {str(e)}")
        messages.error(request, 'An error occurred while loading the dashboard.')
        return redirect('dashboard')
