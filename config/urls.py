from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),#routeur admin django
    path('', include('apps.core.urls')),
    path('alertes/', include('apps.alertes.urls')),
    path('analytics/', include('apps.analytics.urls')),
]
