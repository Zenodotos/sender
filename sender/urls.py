from django.urls import path
from . import views

urlpatterns = [
    # Main views
    path('', views.upload_view, name='upload'),
    path('campaigns/', views.campaigns_view, name='campaigns'),
    path('template/', views.template, name='template'),
    path('campaign-status/<uuid:campaign_id>/', views.campaign_status, name='campaign_status'),
    
    # AJAX endpoints
    path('upload-excel/', views.upload_excel, name='upload_excel'),
    path('create-campaign/', views.create_campaign, name='create_campaign'),
    path('send-campaign/<uuid:campaign_id>/', views.send_campaign, name='send_campaign'),
    
    # API endpoints
    path('api/campaign-status/<uuid:campaign_id>/', views.api_campaign_status, name='api_campaign_status'),
]
