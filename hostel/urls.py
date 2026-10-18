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
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)