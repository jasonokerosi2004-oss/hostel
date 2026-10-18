from django.core.management.base import BaseCommand
from student.services import run_allocation_engine

class Command(BaseCommand):
    help = 'Triggers the priority room allocation service engine.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Initializing priority hostel allocation engine...'))
        
        try:
            allocated_count = run_allocation_engine()
            self.stdout.write(
                self.style.SUCCESS(f'Successfully completed! Rooms allocated to {allocated_count} students.')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Allocation failed due to error: {str(e)}')
            )