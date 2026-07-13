"""URL configuration for Artwork Approval System."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Root shortcuts → artwork app
    path('', RedirectView.as_view(url='/artwork/login/', permanent=False), name='home'),
    path('login/', RedirectView.as_view(url='/artwork/login/', permanent=False), name='root-login'),
    path('dashboard/', RedirectView.as_view(url='/artwork/dashboard/', permanent=False), name='root-dashboard'),
    path('logout/', RedirectView.as_view(url='/artwork/logout/', permanent=False), name='root-logout'),

    # Main application
    path('artwork/', include('artwork.urls')),
]

# Development only — production serves media through authenticated views
if settings.DEBUG and getattr(settings, 'SERVE_MEDIA_PUBLICLY', False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
