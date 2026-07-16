# Generated manually for ProductCategory HOD / deputy mapping

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('artwork', '0005_artworkcolorspec_color_hex'),
    ]

    operations = [
        migrations.AddField(
            model_name='productcategory',
            name='deputy_hod',
            field=models.ForeignKey(
                blank=True,
                help_text='Backup Operations approver; receives the same alerts and can approve.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='product_categories_as_deputy',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Deputy HOD',
            ),
        ),
        migrations.AddField(
            model_name='productcategory',
            name='hod',
            field=models.ForeignKey(
                blank=True,
                help_text='Primary Operations HOD for this product category / department.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='product_categories_as_hod',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Operations HOD',
            ),
        ),
    ]
