# core/urls.py
from django.urls import path
from .views import ContactFormView, WatermarkToolView

urlpatterns = [
    path('contato/', ContactFormView.as_view(), name='contact-form'),
    path('watermark-tool/', WatermarkToolView.as_view(), name='watermark-tool'),
]