from rest_framework import serializers
from .models import Supplier, TestType

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'name']

class TestTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestType
        fields = ['id', 'name']

class SupplierCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id','name']
        
class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'name']

    def create(self, validated_data):
        # Allow setting of ID if provided, but ensure it doesn't conflict
        supplier_id = validated_data.get('id')
        if supplier_id and Supplier.objects.filter(id=supplier_id).exists():
            raise serializers.ValidationError("Supplier with this ID already exists.")
        return super().create(validated_data)