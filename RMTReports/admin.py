from django.contrib import admin
from .models import (
    Supplier, Plant,  Material, SubCategory, Test,ApprovedManagement, MaterialType,
    RawMaterialType, PackingMaterialType,  
    TestResult, RawMaterialTestReport,Report, RMTRRequest, IMP_RMTRRequest,)

# Ensure no duplicate registration of Supplier
try:
    admin.site.unregister(Supplier)
except admin.sites.AlreadyRegistered:
    pass

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    # Correctly reference the 'supplier_email' field
    list_display = ('name', 'supplier_email')  # Correct field names
    search_fields = ('name', 'supplier_email') 

@admin.register(Plant)
class PlantAdmin(admin.ModelAdmin):
    list_display = ('name', 'hod')
    search_fields = ('name', 'hod')  # Adding search fields to improve admin usability


@admin.register(ApprovedManagement)
class ApprovedManagementAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ['name']

@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'material']

@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ['name', 'sub_category']
"""    
@admin.register(Sensitivity)
class SensitivityAdmin(admin.ModelAdmin):
    list_display = ['name']   
"""
@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):
    list_display = ('tests_carried_out', 'sample_results', 'raw_materials_result', 'kapa_standards', 'image_preview')

    def image_preview(self, obj):
        return f'<img src="{obj.image.url}" width="50" height="50">' if obj.image else 'No Image'
    
    image_preview.allow_tags = True  # Allow HTML rendering for the image
    image_preview.short_description = 'Image Preview'  # Custom column name

    search_fields = ('tests_carried_out', 'sample_results', 'raw_materials_result')

"""
admin.site.register(RawMaterialTestReport)
class RawMaterialTestReportAdmin(admin.ModelAdmin):
    list_display = ['rmtr_no', 'get_date', 'get_supplier', 'get_plant', 'get_material_type', 'get_test_type']
    list_filter = ['date', 'supplier', 'plant', 'material_type', 'test_type']
    search_fields = ['rmtr_no', 'supplier__name', 'plant__name', 'material_type__name', 'test_type__name']

    def get_date(self, obj):
        return obj.date

    def get_supplier(self, obj):
        return obj.supplier.name

    def get_plant(self, obj):
        return obj.plant.name

    def get_material_type(self, obj):
        return obj.material_type.name

    def get_test_type(self, obj):
        return obj.test_type.name

    get_date.short_description = 'Date'
    get_supplier.short_description = 'Supplier'
    get_plant.short_description = 'Plant'
    get_material_type.short_description = 'Material Type'
    get_test_type.short_description = 'Test Type'
"""
   
class ReportAdmin(admin.ModelAdmin):
    list_display = ( 'title', 'status', 'created_by', 'modified_by', 'created_at', 'modified_at')
    search_fields = ('title', 'created_by__username', 'modified_by__username')

admin.site.register(Report, ReportAdmin)  
 
admin.site.register(RMTRRequest)
class RMTRRequestAdmin(admin.ModelAdmin):
    list_display = ['rmtr_no', 'get_date', 'get_supplier', 'get_plant', 'get_material_type', 'get_test_type']
    list_filter = ['date', 'supplier', 'plant', 'material_type', 'test_type']
    search_fields = ['rmtr_no', 'supplier__name', 'plant__name', 'material_type__name', 'test_type__name']

    def get_date(self, obj):
        return obj.date

    def get_supplier(self, obj):
        return obj.supplier.name

    def get_plant(self, obj):
        return obj.plant.name

    def get_material_type(self, obj):
        return obj.material_type.name

    def get_test_type(self, obj):
        return obj.test_type.name

    get_date.short_description = 'Date'
    get_supplier.short_description = 'Supplier'
    get_plant.short_description = 'Plant'
    get_material_type.short_description = 'Material Type'
    get_test_type.short_description = 'Test Type'


admin.site.register(IMP_RMTRRequest)
class IMP_RMTRRequestAdmin(admin.ModelAdmin):
    list_display = ['imp_rmtr_no', 'get_date', 'get_supplier', 'get_plant', 'get_material_type', 'get_test_type']
    list_filter = ['date', 'supplier', 'plant', 'material_type', 'test_type']
    search_fields = ['imp_rmtr_no', 'supplier__name', 'plant__name', 'material_type__name', 'test_type__name']

    def get_date(self, obj):
        return obj.date

    def get_supplier(self, obj):
        return obj.supplier.name

    def get_plant(self, obj):
        return obj.plant.name

    def get_material_type(self, obj):
        return obj.material_type.name

    def get_test_type(self, obj):
        return obj.test_type.name

    get_date.short_description = 'Date'
    get_supplier.short_description = 'Supplier'
    get_plant.short_description = 'Plant'
    get_material_type.short_description = 'Material Type'
    get_test_type.short_description = 'Test Type'


