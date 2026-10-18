from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.caretaker_dashboard, name='caretaker_dashboard'),
    path('checkin/<int:allocation_id>/', views.process_physical_checkin, name='process_physical_checkin'),
    path('defect/new/', views.log_room_defect, name='log_room_defect'),
    path('scanner/', views.gate_scanner, name='gate_scanner'), # <-- Add this line
path('checkout/<int:allocation_id>/', views.process_checkout, name='process_checkout'),
path('hall/rooms/', views.hall_room_list, name='hall_room_list'),
path('room/<int:room_id>/repair/', views.mark_room_under_repair, name='mark_room_under_repair'),
path('room/<int:room_id>/service/', views.return_room_to_service, name='return_room_to_service'),
path('room/<int:room_id>/inspect/', views.conduct_room_inspection, name='conduct_room_inspection'),
]