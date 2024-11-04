from django.urls import path
from .views import MakeCallView, HangupCallView, UpdateSIPConfiguration

urlpatterns = [
    path('make-call/', MakeCallView.as_view(), name='make-call'),
    path('hangup-call/', HangupCallView.as_view(), name='hangup-call'),
    path('update-sip-config/', UpdateSIPConfiguration.as_view(), name='update_sip_configuration'),
]