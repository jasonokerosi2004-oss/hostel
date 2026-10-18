from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.officer_dashboard, name='officer_dashboard'),
    path('execute-allocations/', views.execute_allocations, name='execute_allocations'),
    path('reset-system/', views.reset_system_data, name='reset_system'),
    path('transfer/approve/<int:request_id>/', views.approve_transfer, name='approve_transfer'),
    path('transfer/reject/<int:request_id>/', views.reject_transfer, name='reject_transfer'),
    path('applications/', views.view_applications, name='view_applications'),
    path('transfers/', views.view_transfers, name='view_transfers'),
    path('waitlist/', views.view_waiting_list, name='view_waiting_list'),
path('waitlist/promote/<int:waitlist_id>/', views.promote_from_waitlist, name='promote_from_waitlist'),
path('waitlist/remove/<int:waitlist_id>/', views.remove_from_waitlist, name='remove_from_waitlist'),
path('occupancy-inspector/', views.room_occupancy_inspector, name='room_occupancy_inspector'),
path('reports/', views.view_reports, name='view_reports'),
path('reports/generate/', views.generate_occupancy_report, name='generate_occupancy_report'),
path('students/', views.manage_students, name='manage_students'),
path('analytics/', views.occupancy_analytics, name='occupancy_analytics'),
path('maintenance/', views.view_maintenance_logs, name='view_maintenance_logs'),
path('maintenance/update/<int:log_id>/', views.update_maintenance_status, name='update_maintenance_status'),
path('broadcast/', views.broadcast_notifications, name='broadcast_notifications'),
path('clearance/pass/<int:allocation_id>/', views.digital_clearance_pass, name='digital_clearance_pass'),
path('gate-logs/', views.gate_audit_trail, name='gate_audit_trail'),
path('applications/clear/<int:application_id>/', views.clear_ineligible_application, name='clear_ineligible_application'),
path('remove-from-waitlist/<int:waitlist_id>/', views.remove_from_waitlist, name='remove_from_waitlist'),
]