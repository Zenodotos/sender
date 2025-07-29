from django.urls import path
from . import views

urlpatterns = [
    # Main views
    path('upload/', views.upload_view, name='upload'),
    path('', views.campaigns_view, name='campaigns'),
    path('template/', views.template, name='template'),
    path('campaign-status/<uuid:campaign_id>/', views.campaign_status, name='campaign_status'),
    path('edit-campaign/<uuid:campaign_id>/', views.edit_campaign, name='edit_campaign'),
    
    # AJAX endpoints
    path('upload-excel/', views.upload_excel, name='upload_excel'),
    path('create-campaign/', views.create_campaign, name='create_campaign'),
    path('send-campaign/<uuid:campaign_id>/', views.send_campaign, name='send_campaign'),
    path('delete-campaign/<uuid:campaign_id>/', views.delete_campaign, name='delete_campaign'),
    path('duplicate-campaign/<uuid:campaign_id>/', views.duplicate_campaign, name='duplicate_campaign'),
    
    # API endpoints
    path('api/campaign-status/<uuid:campaign_id>/', views.api_campaign_status, name='api_campaign_status'),
]