import os
from django.apps import AppConfig

class StudentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'student'

    def ready(self):
        # Only run this on Render cloud deployment
        if os.environ.get('RENDER'):
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            # Credentials for your Render superuser
            username = 'admin'
            email = 'jasonokerosi2004@gmail.com'
            password = 'admin'  # Change to your preferred admin password

            if not User.objects.filter(username=username).exists():
                User.objects.create_superuser(
                    username=username,
                    email=email,
                    password=password
                )
                print("Superuser 'admin' created successfully on Render!")