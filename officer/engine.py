from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from student.models import Application, Allocation, Room, WaitingList

def calculate_priority_score(application):
    student = application.student
    
    # Ineligibility checks: Students lacking fee clearance or flagged with disciplinary issues get 0 score
    if not student.fee_clearance or student.disciplinary_status:
        return 0  
        
    score = 0
    if student.home_distance:
        score += min(student.home_distance // 50, 40)
    
    year_weights = {4: 30, 3: 20, 2: 15, 1: 10}
    score += year_weights.get(student.year_of_study, 10)
    
    # Previous semester occupancy bonus
    if student.held_previous_semester:
        score += 25
        
    return score

@transaction.atomic
def run_allocation_engine():
    # 1. Fetch pending/submitted applications once with related student and roommate data
    pending_apps = list(
        Application.objects.filter(
            Q(status__iexact='PENDING') | Q(status__iexact='Submitted')
        ).select_related('student', 'preferred_roommate')
    )
    
    if not pending_apps:
        return 0

    # 2. Pre-fetch all rooms and map their current active occupancy in memory to prevent N+1 queries
    rooms_dict = {}
    for room in Room.objects.select_related('hall').all():
        active_allocations = list(
            Allocation.objects.filter(
                room=room, 
                status__in=['Pending', 'Confirmed', 'Active']
            ).select_related('application__student')
        )
        
        occupant_genders = set(alloc.application.student.gender for alloc in active_allocations)
        
        rooms_dict[room.room_id] = {
            'room_obj': room,
            'hall_name': room.hall.hall_name,
            'gender_policy': room.hall.gender_policy,
            'room_type': room.room_type,
            'bed_capacity': room.bed_capacity,
            'occupied_beds': len(active_allocations),
            'occupant_genders': occupant_genders
        }

    # 3. Score and sort applications in Python (O(N log N))
    scored_applications = []
    ineligible_apps = []

    for app in pending_apps:
        score = calculate_priority_score(app)
        if score > 0:
            scored_applications.append((score, app))
        else:
            app.status = 'INELIGIBLE'
            ineligible_apps.append(app)

    # Bulk update ineligible applications
    if ineligible_apps:
        Application.objects.bulk_update(ineligible_apps, ['status'])

    scored_applications.sort(key=lambda x: x[0], reverse=True)
    
    allocated_count = 0
    processed_students = set()

    # Lists for high-efficiency bulk creation at the end
    allocations_to_create = []
    waitlists_to_create = []
    apps_to_update = []

    deadline = timezone.now() + timedelta(days=7)

    # Helper function to find an eligible room in memory respecting all constraints
    def find_room_in_memory(student_gender, target_hall=None, room_type_pref=None, beds_needed=1):
        for r_id, r_data in rooms_dict.items():
            # Check remaining bed capacity
            free_beds = r_data['bed_capacity'] - r_data['occupied_beds']
            if free_beds < beds_needed:
                continue
            
            # Check hall gender policy ('Male', 'Female', or 'Mixed')
            policy = r_data['gender_policy'].lower()
            if policy != 'mixed' and policy != student_gender.lower():
                continue
                
            # Check strict room-level gender segregation (no opposite gender in the same room)
            if r_data['occupant_genders']:
                opposite_gender = 'Female' if student_gender == 'Male' else 'Male'
                if opposite_gender in r_data['occupant_genders']:
                    continue
            
            # Check target hall preference if specified
            if target_hall and r_data['hall_name'].strip().lower() != target_hall.strip().lower():
                continue
                
            # Check room type preference if specified
            if room_type_pref and r_data['room_type'].strip().lower() != room_type_pref.strip().lower():
                continue
                
            return r_data
            
        # Fallback search without strict hall/type filters if initial preference search failed
        if target_hall or room_type_pref:
            return find_room_in_memory(student_gender, target_hall=None, room_type_pref=None, beds_needed=beds_needed)
            
        return None

    # 4. Single-pass allocation loop
    for score, app in scored_applications:
        student = app.student
        if student.student_id in processed_students:
            continue
            
        assigned_room_data = None
        roommate_app = None
        pair_allocated = False

        # Handle Roommate Pairing
        if app.preferred_roommate:
            roommate = app.preferred_roommate
            
            # Enforce strict same-gender pairing
            if roommate.gender == student.gender and roommate.student_id not in processed_students:
                # Find roommate application from pre-fetched list
                roommate_app = next((a for a in pending_apps if a.student_id == roommate.student_id), None)
                
                if not roommate_app:
                    roommate_app = Application.objects.filter(
                        student=roommate,
                        status__in=['PENDING', 'Submitted']
                    ).first()

                if roommate_app:
                    roommate_score = calculate_priority_score(roommate_app)
                    if roommate_score > 0:
                        # Look for a room with at least 2 beds available
                        assigned_room_data = find_room_in_memory(
                            student.gender,
                            target_hall=app.preferred_hall,
                            room_type_pref=app.preferred_room_type,
                            beds_needed=2
                        )

                        if assigned_room_data:
                            room_obj = assigned_room_data['room_obj']
                            
                            # Prepare allocations for both friends
                            allocations_to_create.append(Allocation(
                                application=app, room=room_obj, confirmation_deadline=deadline, status='Pending'
                            ))
                            allocations_to_create.append(Allocation(
                                application=roommate_app, room=room_obj, confirmation_deadline=deadline, status='Pending'
                            ))
                            
                            app.status = 'APPROVED'
                            roommate_app.status = 'APPROVED'
                            apps_to_update.extend([app, roommate_app])
                            
                            processed_students.add(student.student_id)
                            processed_students.add(roommate.student_id)
                            allocated_count += 2
                            pair_allocated = True

                            # Update in-memory room tracking
                            assigned_room_data['occupied_beds'] += 2
                            assigned_room_data['occupant_genders'].add(student.gender)

        # If a pair could not fit together (e.g., only 1 bed left), they fall through 
        # to individual allocation fallback in the exact same pass.
        if pair_allocated:
            continue

        # Single Student Allocation Fallback
        assigned_room_data = find_room_in_memory(
            student.gender,
            target_hall=app.preferred_hall,
            room_type_pref=app.preferred_room_type,
            beds_needed=1
        )

        if assigned_room_data:
            room_obj = assigned_room_data['room_obj']
            allocations_to_create.append(Allocation(
                application=app, room=room_obj, confirmation_deadline=deadline, status='Pending'
            ))
            app.status = 'APPROVED'
            apps_to_update.append(app)
            
            processed_students.add(student.student_id)
            allocated_count += 1

            # Update in-memory room tracking
            assigned_room_data['occupied_beds'] += 1
            assigned_room_data['occupant_genders'].add(student.gender)
        else:
            # Waitlist fallback if no gender-compatible room is available
            waitlists_to_create.append(WaitingList(
                student=student, priority_score=score
            ))
            app.status = 'WAITLISTED'
            apps_to_update.append(app)
            processed_students.add(student.student_id)

    # 5. Bulk database write operations for maximum efficiency and speed
    if allocations_to_create:
        Allocation.objects.bulk_create(allocations_to_create)
    if waitlists_to_create:
        WaitingList.objects.bulk_create(waitlists_to_create)
    if apps_to_update:
        Application.objects.bulk_update(apps_to_update, ['status'])

    # Synchronize room occupancy status back to the database tables
    for r_id, r_data in rooms_dict.items():
        if r_data['occupied_beds'] >= r_data['bed_capacity']:
            r_data['room_obj'].occupancy_status = 'Occupied'
            r_data['room_obj'].save(update_fields=['occupancy_status'])

    return allocated_count