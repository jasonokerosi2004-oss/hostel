from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Q, F
from .models import Application, Allocation, Room, WaitingList

def calculate_priority_score(application):
    student = application.student
    
    # Ineligibility checks based on your student model fields
    if not student.fee_clearance or student.disciplinary_status:
        return 0  
        
    score = 0
    if student.home_distance:
        score += min(student.home_distance // 50, 40)
    
    year_weights = {4: 30, 3: 20, 2: 15, 1: 10}
    score += year_weights.get(student.year_of_study, 10)
    return score

@transaction.atomic
def run_allocation_engine():
    # Fetch pending/submitted applications and prefetch student data
    pending_apps = Application.objects.filter(
        Q(status__iexact='PENDING') | Q(status__iexact='Submitted')
    ).select_related('student')
    
    scored_applications = []
    for app in pending_apps:
        score = calculate_priority_score(app)
        if score > 0:
            scored_applications.append((score, app))
        else:
            app.status = 'INELIGIBLE'
            app.save()

    # Sort applications by priority score (highest score first)
    scored_applications.sort(key=lambda x: x[0], reverse=True)
    
    allocated_count = 0
    for score, app in scored_applications:
        student = app.student
        
        # Base query for rooms with available space (active allocations < bed_capacity)
        rooms_query = Room.objects.annotate(
            active_count=Count(
                'allocation', 
                filter=Q(allocation__status__in=['Pending', 'Confirmed', 'Active'])
            )
        ).filter(active_count__lt=F('bed_capacity'))
        
        # Enforce gender policy matching (Hall gender policy vs Student gender)
        rooms_query = rooms_query.filter(
            Q(hall__gender_policy__iexact='Mixed') | 
            Q(hall__gender_policy__iexact=student.gender)
        )
        
        available_room = None
        
        # 1. Try to match preferred hall name (since preferred_hall is a CharField)
        if app.preferred_hall:
            available_room = rooms_query.filter(
                hall__hall_name__iexact=app.preferred_hall.strip()
            ).first()
            
        # 2. Fallback: If preferred hall is full or doesn't match, grab any valid available room
        if not available_room:
            available_room = rooms_query.first()
        
        if available_room:
            # Create the allocation linked to the application (satisfies Allocation model foreign key)
            Allocation.objects.create(
                application=app,
                room=available_room,
                confirmation_deadline=timezone.now() + timedelta(days=7),
                status='Pending'
            )
            app.status = 'APPROVED'
            app.save()
            
            allocated_count += 1
        else:
            # Add to waiting list if no rooms match
            WaitingList.objects.get_or_create(
                student=student,
                defaults={'priority_score': score}
            )
            app.status = 'WAITLISTED'
            app.save()
            
    return allocated_count