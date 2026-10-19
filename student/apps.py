import os
from django.apps import AppConfig
from django.db.utils import OperationalError, ProgrammingError

class StudentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'student'

    def ready(self):
        # Only run this on Render cloud deployment
        if os.environ.get('RENDER'):
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                
                username = 'admin'
                email = 'jasonokerosi2004@gmail.com'
                password = 'admin'

                if not User.objects.filter(username=username).exists():
                    User.objects.create_superuser(
                        username=username,
                        email=email,
                        password=password
                    )
                    print("Superuser 'admin' created successfully on Render!")
            except (OperationalError, ProgrammingError):
                # Safely pass if tables haven't been created by migrate yet
                pass