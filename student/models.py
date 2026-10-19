from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

class Hall(models.Model):
    hall_id = models.AutoField(primary_key=True)
    hall_name = models.CharField(max_length=100, unique=True)
    gender_policy = models.CharField(max_length=20) # e.g., 'Male', 'Female', 'Mixed'
    total_capacity = models.IntegerField()

    def __str__(self):
        return self.hall_name

class Room(models.Model):
    room_id = models.AutoField(primary_key=True)
    hall = models.ForeignKey(Hall, on_delete=models.CASCADE, db_column='hall_id')
    room_number = models.CharField(max_length=20)
    room_type = models.CharField(max_length=50) # e.g., 'Single', 'Double'
    occupancy_status = models.CharField(max_length=30, default='Available')
    bed_capacity = models.IntegerField()

    def __str__(self):
        return f"{self.hall.hall_name} Room {self.room_number}"

class Student(models.Model):
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
    ]
    
    YEAR_CHOICES = [
        (1, 'Year 1'),
        (2, 'Year 2'),
        (3, 'Year 3'),
        (4, 'Year 4'),
    ]
    
    student_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    reg_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    full_name = models.CharField(max_length=150, null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, null=True, blank=True) 
    year_of_study = models.IntegerField(choices=YEAR_CHOICES, null=True, blank=True)
    home_distance = models.FloatField(null=True, blank=True)
    fee_clearance = models.BooleanField(default=False)
    disciplinary_status = models.BooleanField(default=False)
    held_previous_semester = models.BooleanField(default=False)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    
    def __str__(self):
        return f"{self.full_name or 'Unassigned'} ({self.reg_number or 'No Reg'})"

class Announcement(models.Model):
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Application(models.Model):
    application_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        Student, 
        on_delete=models.CASCADE, 
        related_name='applications', 
        db_column='student_id'
    )
    submission_date = models.DateTimeField(auto_now_add=True)
    preferred_hall = models.CharField(max_length=100)
    preferred_room_type = models.CharField(max_length=50, blank=True, null=True)
    
    preferred_roommate = models.ForeignKey(
        Student, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='requested_as_roommate', 
        db_column='preferred_roommate_id'
    )
    
    status = models.CharField(max_length=30, default='Submitted')

    def get_ineligibility_reason(self):
        reasons = []
        if not self.student.fee_clearance:
            reasons.append("Fee clearance is pending ❌")
        if self.student.disciplinary_status:
            reasons.append("Active disciplinary flag on record ⚠️")
        return " | ".join(reasons) if reasons else "Did not meet priority criteria."

    def __str__(self):
        return f"App #{self.application_id} - {self.student.reg_number}"

class Caretaker(models.Model):
    caretaker_id = models.AutoField(primary_key=True)
    hall = models.ForeignKey(Hall, on_delete=models.CASCADE, db_column='hall_id')
    name = models.CharField(max_length=150)
    contact_info = models.CharField(max_length=100)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"Caretaker: {self.name} ({self.hall.hall_name})"

class AccommodationOfficer(models.Model):
    officer_id = models.AutoField(primary_key=True)
    staff_credentials = models.CharField(max_length=100, unique=True)
    department = models.CharField(max_length=100)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"Officer: {self.staff_credentials}"

class Allocation(models.Model):
    allocation_id = models.AutoField(primary_key=True)
    application = models.ForeignKey(Application, on_delete=models.CASCADE, db_column='application_id')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, db_column='room_id')
    timestamp = models.DateTimeField(auto_now_add=True)
    confirmation_deadline = models.DateTimeField()
    status = models.CharField(max_length=30, default='Pending')

    def __str__(self):
        return f"Allocation #{self.allocation_id} - {self.status}"

class WaitingList(models.Model):
    queue_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, db_column='student_id')
    priority_score = models.FloatField(default=0.0)
    entry_timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Queue #{self.queue_id} Score: {self.priority_score}"

class TransferRequest(models.Model):
    request_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, db_column='student_id')
    reason = models.TextField(blank=True, null=True)
    requested_preference = models.CharField(max_length=150)
    status = models.CharField(max_length=30, default='Submitted')

    def __str__(self):
        return f"Transfer #{self.request_id} - {self.student.reg_number}"

class MaintenanceLog(models.Model):
    log_id = models.AutoField(primary_key=True)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, db_column='room_id')
    description = models.TextField()
    severity = models.CharField(max_length=30)
    reported_date = models.DateField(auto_now_add=True)
    repair_status = models.CharField(max_length=30, default='Open')
    damage_penalty_amount = models.FloatField(default=0.0)

    @property
    def resident_student(self):
        active_allocation = Allocation.objects.filter(room=self.room, status='Active').first()
        if active_allocation:
            return active_allocation.application.student
        return None

    def __str__(self):
        return f"Log #{self.log_id} Room {self.room.room_number} ({self.repair_status})"

class OccupancyReport(models.Model):
    report_id = models.AutoField(primary_key=True)
    officer = models.ForeignKey(AccommodationOfficer, on_delete=models.CASCADE, db_column='officer_id')
    semester = models.CharField(max_length=50)
    free_rooms_count = models.IntegerField()
    unallocated_students_count = models.IntegerField()
    penalty_summary = models.TextField()

    def __str__(self):
        return f"Report {self.semester} by {self.officer.staff_credentials}"
    
class Notification(models.Model):
    notification_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, db_column='student_id')
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification for {self.student.reg_number}: {self.title}"

class GateLog(models.Model):
    log_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    allocation = models.ForeignKey(Allocation, on_delete=models.CASCADE)
    scan_type = models.CharField(max_length=10, choices=[('ENTRY', 'Entry'), ('EXIT', 'Exit')])
    timestamp = models.DateTimeField(auto_now_add=True)
    gate_name = models.CharField(max_length=100, default="Main Hostel Gate")

    def __str__(self):
        return f"{self.student.reg_number} - {self.scan_type} at {self.timestamp}"

class CheckInLog(models.Model):
    log_id = models.AutoField(primary_key=True)
    allocation = models.OneToOneField(Allocation, on_delete=models.CASCADE, db_column='allocation_id')
    checked_in_at = models.DateTimeField(auto_now_add=True)
    key_issued = models.BooleanField(default=False)
    inventory_verified = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Check-In: {self.allocation.application.student.reg_number} Room {self.allocation.room.room_number}"

class RoomInspection(models.Model):
    inspection_id = models.AutoField(primary_key=True)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, db_column='room_id')
    caretaker = models.ForeignKey(Caretaker, on_delete=models.CASCADE, db_column='caretaker_id')
    inspection_date = models.DateTimeField(auto_now_add=True)
    furniture_rating = models.CharField(max_length=20, default='Good')
    electrical_rating = models.CharField(max_length=20, default='Good')
    plumbing_rating = models.CharField(max_length=20, default='Good')
    damage_charges = models.FloatField(default=0.0)
    remarks = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Inspection #{self.inspection_id} Room {self.room.room_number} ({self.inspection_date.strftime('%Y-%m-%d')})"