from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('artwork', '0003_packagingsupplier'),
    ]

    operations = [
        migrations.AlterField(
            model_name='artworkrequest',
            name='product_name',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
    ]
