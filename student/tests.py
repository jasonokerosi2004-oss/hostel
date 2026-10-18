from django.test import TestCase
from .models import Hall, Room, Student, Application, Allocation, WaitingList
from .services import run_allocation_engine

class AllocationEngineTestCase(TestCase):
    
    def setUp(self):
        """Step 1: Create a controlled testing environment matching your actual models"""
        self.hall = Hall.objects.create(
            hall_name="Block A", 
            gender_policy="Female", 
            total_capacity=10
        )
        self.room = Room.objects.create(
            hall=self.hall, 
            room_number="101", 
            room_type="Single",
            bed_capacity=1
        )
        self.student = Student.objects.create(
            reg_number="REG001",
            full_name="Sarah Test", 
            gender="Female",
            year_of_study=2,
            home_distance=50.0,
            fee_clearance=True,
            disciplinary_status=False
        )
        self.application = Application.objects.create(
            student=self.student,
            preferred_hall="Block A",
            status="Submitted"
        )

    def test_successful_allocation(self):
        """Step 2 & 3: Run the engine and verify the student gets the room"""
        allocated_count = run_allocation_engine()
        
        # Check scoreboard
        self.assertEqual(allocated_count, 1)
        
        # Check application status (Fixed to uppercase 'APPROVED')
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'APPROVED')
        
        # Verify Allocation record was created
        allocation = Allocation.objects.get(application=self.application)
        self.assertEqual(allocation.room, self.room)

    def test_gender_policy_rejection(self):
        """Test that a male student cannot be placed in a female-only hall"""
        male_student = Student.objects.create(
            reg_number="REG002",
            full_name="John Test", 
            gender="Male",
            year_of_study=2,
            home_distance=40.0,
            fee_clearance=True,
            disciplinary_status=False
        )
        male_app = Application.objects.create(
            student=male_student,
            preferred_hall="Block A",
            status="Submitted"
        )
        
        run_allocation_engine()
        
        # Verify he was sent to the waiting list instead
        male_app.refresh_from_db()
        self.assertTrue(WaitingList.objects.filter(student=male_student).exists())