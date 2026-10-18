from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Student Portal Dashboard & Profile
    path('dashboard/', views.student_dashboard, name='student_dashboard'),
    
    # Room Application & Allocation Routes
    path('apply/', views.apply_room, name='apply_room'),
    path('allocation/confirm/', views.confirm_allocation, name='confirm_allocation'),
    
    # Additional student portal links (adjust names if needed based on your views)
    path('transfer/', views.request_transfer, name='request_transfer'),  # <--- Add this line for transfer request
    path('logout/', views.custom_logout_view, name='logout'),
    
]
