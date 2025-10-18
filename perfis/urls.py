# perfis/urls.py
from django.urls import path
from .views import FotografoListView

urlpatterns = [
    path('fotografos/', FotografoListView.as_view(), name='fotografo-list-public'),
]