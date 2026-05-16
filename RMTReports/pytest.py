"""def test_request(request):
    if request.method == 'POST':
        logger.info("Form data received from multiple pages")
        logger.info(request.POST)  

        # Fetch or create the RMTRRequest instance
        rmtr_no = request.POST.get('rmtr_no')
        if rmtr_no:
            request_instance = get_object_or_404(RMTRRequest, rmtr_no=rmtr_no)
        else:
            request_instance = RMTRRequest()  # Create a new instance if necessary
        
        # Collect primary form data from the main page
        form_data = {
            'rmtr_no': generate_rmtr_number(request),  
            'date': request.POST.get('date'),
            'supplier': request.POST.get('supplier'),
            'material': request.POST.get('material'),
            'sub_category': request.POST.get('sub_category'),
            'tests': request.POST.get('tests'),
            'priority': request.POST.get('priority'),
            'sensitivity': request.POST.get('sensitivity'),
            'specs': request.POST.get('specs'),
            'plant': request.POST.get('plant'),
            'quantity': request.POST.get('quantity'),
            'hod': request.POST.get('hod'),
            'image_upload': request.POST.get('image_upload'),
            'approved_mgt': request.POST.get('approved-mgt'),
            'justification': request.POST.get('justification'),
            'material_type': request.POST.get('material-type'),
            'requested_by': request.POST.get('requested-by'),
        }

        # Update RMTRRequest fields
        for field, value in form_data.items():
            if value is not None:
                setattr(request_instance, field, value)

        # Save RMTRRequest instance
        request_instance.save()

        # Handle additional data for related models
        if 'tests_done_by' in request.POST:
            test_results, created = TestResults.objects.get_or_create(request=request_instance)
            test_results.tests_done_by = request.POST.get('tests_done_by')
            # Update other test results fields as needed
            test_results.tests_carried_out = request.POST.get('tests_carried_out', [])
            test_results.sample_results = request.POST.get('sample_results', [])
            test_results.raw_material_results = request.POST.get('raw_material_results', [])
            test_results.kapa_standards = request.POST.get('kapa_standards', [])
            test_results.lab_qc_comments = request.POST.get('lab_qc_comments', '')
            if 'test_image' in request.FILES:
                test_results.test_image = request.FILES['test_image']
            test_results.save()

        if 'hod_approval' in request.POST:
            hod_approval, created = HODApproval.objects.get_or_create(request=request_instance)
            hod_approval.comments = request.POST.get('hod_comments', '')
            hod_approval.approved = request.POST.get('hod_approved') == 'true'
            hod_approval.rejected = request.POST.get('hod_rejected') == 'true'
            hod_approval.save()

        if 'management_approval' in request.POST:
            management_approval, created = ManagementApproval.objects.get_or_create(request=request_instance)
            management_approval.comments = request.POST.get('management_comments', '')
            management_approval.approved = request.POST.get('management_approved') == 'true'
            management_approval.rejected = request.POST.get('management_rejected') == 'true'
            management_approval.save()

        if 'fm_approval' in request.POST:
            fm_approval, created = FMApproval.objects.get_or_create(request=request_instance)
            fm_approval.comments = request.POST.get('fm_comments', '')
            fm_approval.approved = request.POST.get('fm_approved') == 'true'
            fm_approval.rejected = request.POST.get('fm_rejected') == 'true'
            fm_approval.save()

        # Add additional related approvals as needed

        messages.success(request, 'Data submitted successfully.')
        return JsonResponse({'status': 'success', 'redirect': '/pending_reports/'})

    return render(request, 'test_request.html')
"""
