from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('artwork', '0002_productcategory'),
    ]

    operations = [
        migrations.CreateModel(
            name='PackagingSupplier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('display_order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name_plural': 'Packaging suppliers',
                'ordering': ['display_order', 'name'],
            },
        ),
    ]
