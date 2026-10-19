from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from student import views as student_views

urlpatterns = [
    # Root URL path: Loads the login page directly when visiting the homepage
    path('', auth_views.LoginView.as_view(template_name='student/login.html'), name='home_login'),

    path('admin/', admin.site.urls),
    
    # Authentication routes
    path('accounts/login/', auth_views.LoginView.as_view(template_name='student/login.html'), name='login'),
    
    # FIX: Use custom_logout_view here instead of LogoutView.as_view()
    path('accounts/logout/', student_views.custom_logout_view, name='logout'),
    path('logout/', student_views.custom_logout_view, name='logout'),
    
    # Portal routes
    path('student/', include('student.urls')),
    path('officer/', include('officer.urls')),
    path('caretaker/', include('caretaker.urls')),
    path('login-redirect/', student_views.custom_login_redirect, name='login_redirect'),
    # 1. Enter email to request a reset link
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='student/password_reset.html'), name='password_reset'),
    
    # 2. Success message saying "Check your email"
    path('password_reset/done/', auth_views.PasswordResetView.as_view(template_name='student/password_reset_done.html'), name='password_reset_done'),
    
    # 3. The link clicked from the email (enter new password)
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='student/password_reset_confirm.html'), name='password_reset_confirm'),
    
    # 4. Success message saying "Password changed successfully"
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='student/password_reset_complete.html'), name='password_reset_complete'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)