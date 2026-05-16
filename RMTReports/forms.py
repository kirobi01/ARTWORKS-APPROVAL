from django import forms
from django.apps import apps
from .models import (RMTRRequest, RawMaterialTestReport, RMTR,
                     RawMaterialType, RawMaterialCategory, RawMaterialSubcategory,
                     RawMaterialTest, Report, HODPurchaseApproval,
                     HODApproval, HODTestApproval, ManagementApproval,
                     ManagementTestApproval, FMApproval, FMTestApproval,
                     QAOTestApproval, MilanTestApproval, IMP_RMTRRequest)

#RMTR
class RMTRRequestForm(forms.ModelForm):
    class Meta:
        model = RMTRRequest
        # Exclude fields that should not be edited by the user
        exclude = [
            'hod_purchase_approved', 'hod_purchase_rejected', 'hod_purchase_date_approved', 'hod_purchase_date_rejected',
            'management_approved', 'management_rejected', 'management_date_approved', 'management_date_rejected',
            'fm_approved', 'fm_rejected', 'fm_date_approved', 'fm_date_rejected',
            'hod_approved', 'hod_rejected', 'hod_date_approved', 'hod_date_rejected',
            'qao_approved', 'qao_rejected', 'qao_date_approved', 'qao_date_rejected',
            'hod_test_approved', 'hod_test_rejected', 'hod_test_date_approved', 'hod_test_date_rejected',
            'fm_test_approved', 'fm_test_rejected', 'fm_test_date_approved', 'fm_test_date_rejected',
            'management_test_approved', 'management_test_rejected', 'management_test_date_approved', 'management_test_date_rejected',
            'milan_approved', 'milan_rejected', 'milan_date_approved', 'milan_date_rejected',
            'status', 'date_created'
        ]
        
        # Editable fields
        fields = [
            'rmtr_no', 'supplier', 'date', 'material_type', 'sub_category', 'tests', 
            'plant', 'approved_mgt', 'requested_by', 'justification', 'uom', 'quantity', 
            'specs', 'image', 'hod_purchase_priority', 'hod_purchase_sensitivity', 'hod_purchase_comments',
            'management_comments', 'fm_comments', 'hod_comments', 'test_image', 'lab_qc_comments', 'tests_done_by',
            'qao_comments', 'hod_test_comments', 'fm_test_comments', 'management_test_comments', 'milan_comments',
            'tests_carried_out1', 'sample_results1', 'raw_material_results1', 'kapa_standards1',
            'tests_carried_out2', 'sample_results2', 'raw_material_results2', 'kapa_standards2',
            'tests_carried_out3', 'sample_results3', 'raw_material_results3', 'kapa_standards3',
            'tests_carried_out4', 'sample_results4', 'raw_material_results4', 'kapa_standards4',
            'tests_carried_out5', 'sample_results5', 'raw_material_results5', 'kapa_standards5',
            'tests_carried_out6', 'sample_results6', 'raw_material_results6', 'kapa_standards6',
            'tests_carried_out7', 'sample_results7', 'raw_material_results7', 'kapa_standards7',
            'tests_carried_out8', 'sample_results8', 'raw_material_results8', 'kapa_standards8',
            'tests_carried_out9', 'sample_results9', 'raw_material_results9', 'kapa_standards9',
            'tests_carried_out10', 'sample_results10', 'raw_material_results10', 'kapa_standards10',
            'tests_carried_out11', 'sample_results11', 'raw_material_results11', 'kapa_standards11',
            'tests_carried_out12', 'sample_results12', 'raw_material_results12', 'kapa_standards12',
            'tests_carried_out13', 'sample_results13', 'raw_material_results13', 'kapa_standards13',
            'tests_carried_out14', 'sample_results14', 'raw_material_results14', 'kapa_standards14',
            'tests_carried_out15', 'sample_results15', 'raw_material_results15', 'kapa_standards15',
            'tests_carried_out16', 'sample_results16', 'raw_material_results16', 'kapa_standards16',
        ]

        
        
        # Configure widgets
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'justification': forms.Textarea(attrs={'rows': 3}),
            'specs': forms.TextInput(attrs={'placeholder': 'Specification details'}),
            'hod_purchase_comments': forms.Textarea(attrs={'rows': 3}),
            'management_comments': forms.Textarea(attrs={'rows': 3}),
            'fm_comments': forms.Textarea(attrs={'rows': 3}),
            'hod_comments': forms.Textarea(attrs={'rows': 3}),
            'lab_qc_comments': forms.Textarea(attrs={'rows': 3}),
            'qao_comments': forms.Textarea(attrs={'rows': 3}),
            'hod_test_comments': forms.Textarea(attrs={'rows': 3}),
            'fm_test_comments': forms.Textarea(attrs={'rows': 3}),
            'management_test_comments': forms.Textarea(attrs={'rows': 3}),
            'milan_comments': forms.Textarea(attrs={'rows': 3}),
        }
        
                 
            
        Supplier = apps.get_model('RMTReports', 'Supplier')
        supplier = forms.ModelChoiceField(queryset=Supplier.objects.all())
        
        
        
class RawMaterialTestReportForm(forms.ModelForm):
    class Meta:
        model = RawMaterialTestReport
        fields = [
           
        ]

    # Form fields without dynamic querysets from Django (handled by JS)
    supplier = forms.CharField(required=True)  # This will be passed from the frontend (ID or UUID)
    plant = forms.CharField(required=True)  # This will be passed from the frontend
    approved_management = forms.CharField(required=True)  # Same for this field
    material_type = forms.ChoiceField(choices=[
        ('food_raw_materials', 'Food Raw Materials'),
        ('non_food_raw_materials', 'Non-Food Raw Materials'),
        ('packing_materials', 'Packing Materials')
    ], required=True)

    subcategory = forms.ChoiceField(choices=[], required=True)  # Subcategory choices will be set by JS
    tests = forms.CharField(widget=forms.CheckboxSelectMultiple(), required=True)  # JS will populate test checkboxes

    # Additional form fields for test results and final conclusions
    test_results = forms.CharField(widget=forms.Textarea, required=True)
    final_conclusion = forms.CharField(widget=forms.Textarea, required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Dynamically populate the subcategory choices based on material_type
        if 'material_type' in self.data:
            material_type = self.data.get('material_type')
            if material_type == 'food_raw_materials':
                self.fields['subcategory'].choices = [('food_raw_material_1', 'Food Raw Material 1'),
                                                      ('food_raw_material_2', 'Food Raw Material 2')]
            elif material_type == 'non_food_raw_materials':
                self.fields['subcategory'].choices = [('non_food_raw_material_1', 'Non-Food Raw Material 1'),
                                                      ('non_food_raw_material_2', 'Non-Food Raw Material 2')]
            elif material_type == 'packing_materials':
                self.fields['subcategory'].choices = [('packing_material_1', 'Packing Material 1'),
                                                      ('packing_material_2', 'Packing Material 2')]

        # Update the queryset for tests dynamically based on subcategory (JS will populate these)
        if 'subcategory' in self.data:
            subcategory_id = self.data.get('subcategory')
            self.fields['tests'].choices = RawMaterialTest.objects.filter(subcategory_id=subcategory_id)

    def clean(self):
        cleaned_data = super().clean()
        material_type = cleaned_data.get('material_type')

        # Validate that the necessary fields are selected based on the material_type
        if material_type == 'food_raw_materials' and not cleaned_data.get('raw_material_type'):
            self.add_error('raw_material_type', 'Raw material type must be selected for Food Raw Materials.')
        elif material_type == 'packing_materials' and not cleaned_data.get('packing_material_type'):
            self.add_error('packing_material_type', 'Packing material type must be selected for Packing Materials.')

        # Optionally validate that the tests provided are valid
        tests = cleaned_data.get('tests')
        if tests:
            valid_tests = RawMaterialTest.objects.filter(id__in=tests)
            if len(valid_tests) != len(tests):
                self.add_error('tests', 'Some selected tests are invalid.')

        return cleaned_data

# RMTR Form (Supplier validation based on frontend ID/UUID)
class RMTRForm(forms.ModelForm):
    class Meta:
        model = RMTR
        fields = ['supplier']  # Supplier handled by frontend

    def clean_supplier(self):
        # Assuming the supplier is passed as an ID/UUID
        Supplier = apps.get_model('RMTReports', 'Supplier')
        supplier_id = self.cleaned_data['supplier']
        if not Supplier.objects.filter(id=supplier_id).exists():
            raise forms.ValidationError("Supplier not found.")
        return supplier_id

# RawMaterialType Form
class RawMaterialForm(forms.ModelForm):
    class Meta:
        model = RawMaterialType
        fields = ['name', 'description']

# Report Form
class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = []


# Test Results Form
class TestResultsForm(forms.ModelForm):
    class Meta:
        TestResults = apps.get_model('RMTReports', 'TestResults')
        model = TestResults
        fields = [
            'tests_carried_out', 'sample_results', 
            'raw_material_results', 'kapa_standards', 
            'test_image', 'lab_qc_comments', 'tests_done_by'
        ]
        widgets = {
            'lab_qc_comments': forms.Textarea(attrs={'rows': 3}),
            'tests_carried_out': forms.Textarea(attrs={'rows': 3}),
            'sample_results': forms.Textarea(attrs={'rows': 3}),
            'raw_material_results': forms.Textarea(attrs={'rows': 3}),
            'kapa_standards': forms.Textarea(attrs={'rows': 3}),
        }
# HOD Purchase Approval Form
class HODPurchaseApprovalForm(forms.ModelForm):
    class Meta:
        model = HODPurchaseApproval
        fields = ['hod_purchase_priority', 'hod_purchase_sensitivity', 'hod_purchase_approved', 'hod_purchase_rejected', 'hod_purchase_comments']
        widgets = {
            'hod_purchase_comments': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hod_purchase_approved'].widget.attrs['readonly'] = True
        self.fields['hod_purchase_rejected'].widget.attrs['readonly'] = True
        self.fields['hod_purchase_date_approved'].widget.attrs['readonly'] = True
        self.fields['hod_purchase_date_rejected'].widget.attrs['readonly'] = True

# Management Approval Form
class ManagementApprovalForm(forms.ModelForm):
    class Meta:
        model = ManagementApproval
        fields = ['management_approved','management_date_rejected','management_date_approved', 'management_rejected', 'management_comments']
        widgets = {
            'management_comments': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['management_approved'].widget.attrs['readonly'] = True
        self.fields['management_rejected'].widget.attrs['readonly'] = True
        self.fields['management_date_approved'].widget.attrs['readonly'] = True
        self.fields['management_date_rejected'].widget.attrs['readonly'] = True

# FM Approval Form
class FMApprovalForm(forms.ModelForm):
    class Meta:
        model = FMApproval
        fields = ['hod_plant','fm_approved', 'fm_rejected', 'fm_comments']
        widgets = {
            'fm_comments': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fm_approved'].widget.attrs['readonly'] = True
        self.fields['fm_rejected'].widget.attrs['readonly'] = True
        self.fields['fm_date_approved'].widget.attrs['readonly'] = True
        self.fields['fm_date_rejected'].widget.attrs['readonly'] = True

# HOD Approval Form
class HODApprovalForm(forms.ModelForm):
    class Meta:
        model = HODApproval
        fields = ['hod_approved', 'hod_rejected', 'hod_comments']
        widgets = {
            'hod_comments': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hod_approved'].widget.attrs['readonly'] = True
        self.fields['hod_rejected'].widget.attrs['readonly'] = True
        self.fields['hod_date_approved'].widget.attrs['readonly'] = True
        self.fields['hod_date_rejected'].widget.attrs['readonly'] = True

# QAO Test Approval Form
class QAOTestApprovalForm(forms.ModelForm):
    class Meta:
        model = QAOTestApproval
        fields = ['qao_approved', 'qao_rejected', 'qao_comments']
        widgets = {
            'qao_comments': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['qao_approved'].widget.attrs['readonly'] = True
        self.fields['qao_rejected'].widget.attrs['readonly'] = True
        self.fields['qao_date_approved'].widget.attrs['readonly'] = True
        self.fields['qao_date_rejected'].widget.attrs['readonly'] = True

# HOD Test Approval Form
class HODTestApprovalForm(forms.ModelForm):
    class Meta:
        model = HODTestApproval
        fields = ['hod_test_approved', 'hod_test_rejected', 'hod_test_date_rejected','hod_test_date_approved','hod_test_comments']
        widgets = {
            'hod_test_comments': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hod_test_approved'].widget.attrs['readonly'] = True
        self.fields['hod_test_rejected'].widget.attrs['readonly'] = True
        self.fields['hod_test_date_approved'].widget.attrs['readonly'] = True
        self.fields['hod_test_date_rejected'].widget.attrs['readonly'] = True

# FM Test Approval Form
class FMTestApprovalForm(forms.ModelForm):
    class Meta:
        model = FMTestApproval
        fields = ['fm_test_approved', 'fm_test_rejected','fm_test_date_approved','fm_test_date_rejected', 'fm_test_comments']
        widgets = {
            'fm_test_comments': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fm_test_approved'].widget.attrs['readonly'] = True
        self.fields['fm_test_rejected'].widget.attrs['readonly'] = True
        self.fields['fm_test_date_approved'].widget.attrs['readonly'] = True
        self.fields['fm_test_date_rejected'].widget.attrs['readonly'] = True

# Management Test Approval Form
class ManagementTestApprovalForm(forms.ModelForm):
    class Meta:
        model = ManagementTestApproval
        fields = ['management_test_approved', 'management_test_rejected','management_test_date_approved','management_test_date_rejected', 'management_test_comments']
        widgets = {
            'management_test_comments': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['management_test_approved'].widget.attrs['readonly'] = True
        self.fields['management_test_rejected'].widget.attrs['readonly'] = True
        self.fields['management_test_date_approved'].widget.attrs['readonly'] = True
        self.fields['management_test_date_rejected'].widget.attrs['readonly'] = True

# Milan Test Approval Form
class MilanTestApprovalForm(forms.ModelForm):
    class Meta:
        model = MilanTestApproval
        fields = ['milan_approved', 'milan_rejected','milan_date_approved','milan_date_rejected', 'milan_comments']
        widgets = {
            'milan_comments': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['milan_approved'].widget.attrs['readonly'] = True
        self.fields['milan_rejected'].widget.attrs['readonly'] = True
        self.fields['milan_date_approved'].widget.attrs['readonly'] = True
        self.fields['milan_date_rejected'].widget.attrs['readonly'] = True
        
        
        
        


class IMP_RMTRRequestForm(forms.ModelForm):
    class Meta:
        model = IMP_RMTRRequest
        
        # Exclude fields that should not be edited by the user
        exclude = [
            'date_created', 'created_at', 'updated_at',
            'status', 
            'hod_purchase_approved', 'hod_purchase_rejected', 'hod_purchase_date_approved', 'hod_purchase_date_rejected', 'hod_purchase_by',
            'management_approved', 'management_rejected', 'management_date_approved', 'management_date_rejected', 'management_by',
            'management_approved_2', 'management_rejected_2', 'management_date_approved_2', 'management_date_rejected_2', 'management_by_2',
            'fm_approved', 'fm_rejected', 'fm_date_approved', 'fm_date_rejected', 'fm_by',
            'hod_approved', 'hod_rejected', 'hod_date_approved', 'hod_date_rejected', 'hod_by',
            'qao_approved', 'qao_rejected', 'qao_date_approved', 'qao_date_rejected', 'qao_by',
            'hod_test_approved', 'hod_test_rejected', 'hod_test_date_approved', 'hod_test_date_rejected', 'hod_test_by',
            'fm_test_approved', 'fm_test_rejected', 'fm_test_date_approved', 'fm_test_date_rejected', 'fm_test_by',
            'management_test_approved', 'management_test_rejected', 'management_test_date_approved', 'management_test_date_rejected', 'management_test_by',
            'milan_approved', 'milan_rejected', 'milan_date_approved', 'milan_date_rejected', 'milan_by',
            'retest_requested_by', 'retest_requested_date', 'retest_date', 'retest_history', 'previous_status',
            'current_user'
        ]
        
        # Fields that can be edited
        fields = [
            'imp_rmtr_no', 'supplier', 'material_type', 'sub_category', 'tests', 
            'plant', 'approved_mgt', 'requested_by', 'justification', 'uom', 'quantity', 
            'specs', 'image', 'created_by',
            'hod_purchase_priority', 'hod_purchase_sensitivity', 'hod_purchase_comments',
            'management_comments', 'management_comments_2', 'fm_comments', 'hod_comments',
            'test_image', 'lab_qc_comments', 'tests_done_by',
            'qao_comments', 'hod_test_comments', 'fm_test_comments', 'management_test_comments', 'milan_comments',
            'retest_reason', 'retest_stage',
            'tests_carried_out1', 'sample_results1', 'raw_material_results1', 'kapa_standards1',
            'tests_carried_out2', 'sample_results2', 'raw_material_results2', 'kapa_standards2',
            'tests_carried_out3', 'sample_results3', 'raw_material_results3', 'kapa_standards3',
            'tests_carried_out4', 'sample_results4', 'raw_material_results4', 'kapa_standards4',
            'tests_carried_out5', 'sample_results5', 'raw_material_results5', 'kapa_standards5',
            'tests_carried_out6', 'sample_results6', 'raw_material_results6', 'kapa_standards6',
            'tests_carried_out7', 'sample_results7', 'raw_material_results7', 'kapa_standards7',
            'tests_carried_out8', 'sample_results8', 'raw_material_results8', 'kapa_standards8',
            'tests_carried_out9', 'sample_results9', 'raw_material_results9', 'kapa_standards9',
            'tests_carried_out10', 'sample_results10', 'raw_material_results10', 'kapa_standards10',
            'tests_carried_out11', 'sample_results11', 'raw_material_results11', 'kapa_standards11',
            'tests_carried_out12', 'sample_results12', 'raw_material_results12', 'kapa_standards12',
            'tests_carried_out13', 'sample_results13', 'raw_material_results13', 'kapa_standards13',
            'tests_carried_out14', 'sample_results14', 'raw_material_results14', 'kapa_standards14',
            'tests_carried_out15', 'sample_results15', 'raw_material_results15', 'kapa_standards15',
            'tests_carried_out16', 'sample_results16', 'raw_material_results16', 'kapa_standards16',
        ]
        
        # Configure widgets
        widgets = {
            'justification': forms.Textarea(attrs={'rows': 3}),
            'specs': forms.TextInput(attrs={'placeholder': 'Specification details'}),
            'hod_purchase_comments': forms.Textarea(attrs={'rows': 3}),
            'management_comments': forms.Textarea(attrs={'rows': 3}),
            'management_comments_2': forms.Textarea(attrs={'rows': 3}),
            'fm_comments': forms.Textarea(attrs={'rows': 3}),
            'hod_comments': forms.Textarea(attrs={'rows': 3}),
            'lab_qc_comments': forms.Textarea(attrs={'rows': 3}),
            'qao_comments': forms.Textarea(attrs={'rows': 3}),
            'hod_test_comments': forms.Textarea(attrs={'rows': 3}),
            'fm_test_comments': forms.Textarea(attrs={'rows': 3}),
            'management_test_comments': forms.Textarea(attrs={'rows': 3}),
            'milan_comments': forms.Textarea(attrs={'rows': 3}),
            'retest_reason': forms.Textarea(attrs={'rows': 3}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'uom': forms.TextInput(attrs={'class': 'form-control'}),
            'material_type': forms.TextInput(attrs={'class': 'form-control'}),
            'sub_category': forms.TextInput(attrs={'class': 'form-control'}),
            'tests': forms.TextInput(attrs={'class': 'form-control'}),
            'requested_by': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def clean_imp_rmtr_no(self):
        """Validate IMP number format"""
        imp_rmtr_no = self.cleaned_data.get('imp_rmtr_no')
        if imp_rmtr_no:
            import re
            if not re.match(r'^IMP_\d{4}-\d{4}$', imp_rmtr_no):
                raise forms.ValidationError('Invalid IMP number format. Should be IMP_YYYY-NNNN')
        return imp_rmtr_no

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supplier'].queryset = apps.get_model('RMTReports', 'Supplier').objects.all()
        self.fields['plant'].queryset = apps.get_model('RMTReports', 'Plant').objects.all()
        self.fields['created_by'].widget = forms.HiddenInput()

    def clean(self):
        cleaned_data = super().clean()
        # Add any cross-field validation here if needed
        return cleaned_data