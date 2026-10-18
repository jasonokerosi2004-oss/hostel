from datetime import timedelta
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from student.models import Hall, Room, Student, Application, Allocation, TransferRequest, MaintenanceLog, WaitingList, OccupancyReport, Notification, AccommodationOfficer, GateLog
from .engine import run_allocation_engine
import json
from django.db.models import Count, F, Q
import io
import base64
import qrcode

def officer_dashboard(request):
    # 1. System-wide metrics required by the accommodation office
    total_halls = Hall.objects.all()
    
    # Calculate bed capacity, occupied beds, free beds, and occupancy status per hall
    hall_metrics = []
    for hall in total_halls:
        rooms = Room.objects.filter(hall=hall)
        total_hall_rooms = rooms.count()
        free_rooms_count = rooms.filter(occupancy_status='Available').count()
        
        # Calculate total beds across all rooms in this hall
        total_beds = sum(r.bed_capacity for r in rooms) if rooms.exists() else 0
        
        # Count confirmed/active allocations for this hall's rooms
        occupied_beds = Allocation.objects.filter(
            room__hall=hall, 
            status__in=['Pending', 'Confirmed', 'Active']
        ).count()
        
        available_beds = max(0, total_beds - occupied_beds)
        
        # Determine Hall Occupancy Status Badge
        if total_beds == 0:
            hall_status = 'Empty'
        elif available_beds == 0:
            hall_status = 'Fully Occupied'
        elif occupied_beds > 0:
            hall_status = 'Partially Occupied'
        else:
            hall_status = 'Fully Available'

        hall_metrics.append({
            'hall': hall,
            'total_count': total_hall_rooms,
            'free_count': free_rooms_count,
            'total_beds': total_beds,
            'occupied_beds': occupied_beds,
            'available_beds': available_beds,
            'hall_status': hall_status,
        })

    # 2. Strict Unallocated Students Calculation
    allocated_student_ids = Allocation.objects.filter(
        status__in=['Pending', 'Confirmed', 'Active']
    ).values_list('application__student', flat=True)

    waitlisted_student_ids = WaitingList.objects.values_list('student', flat=True)

    # Exclude students whose applications are marked ineligible, removed, cancelled, or rejected
    excluded_application_statuses = ['INELIGIBLE', 'REMOVED', 'CANCELLED', 'REJECTED']
    excluded_student_ids = Application.objects.filter(
        status__in=excluded_application_statuses
    ).values_list('student_id', flat=True)

    # Strictly filter unallocated students
    unallocated_students = Student.objects.filter(
        applications__status__iexact='Submitted'
    ).exclude(
        student_id__in=allocated_student_ids
    ).exclude(
        student_id__in=waitlisted_student_ids
    ).exclude(
        student_id__in=excluded_student_ids
    ).distinct()

    # 3. Waitlisted students total count and preview list (top 5 ordered by priority)
    waitlisted_students = WaitingList.objects.select_related('student').all().order_by('-priority_score', 'entry_timestamp')
    waitlisted_count = waitlisted_students.count()

    # 4. Pending / Unconfirmed allocations
    unconfirmed_allocations = Allocation.objects.filter(status='Pending')
    
    # 5. Pending transfer requests
    pending_transfers = TransferRequest.objects.filter(status='Submitted')

    # 6. Confirmed room occupants
    confirmed_allocations = Allocation.objects.filter(status__iexact='Confirmed')

    # 7. Ineligible / Rejected applications for officer oversight and review
    ineligible_applications = Application.objects.filter(status__iexact='INELIGIBLE').select_related('student')

    context = {
        'hall_metrics': hall_metrics,
        'unallocated_count': unallocated_students.count(),
        'waitlisted_count': waitlisted_count,
        'waitlisted_preview': waitlisted_students[:5], # <-- Top 5 preview for dashboard table
        'unconfirmed_count': unconfirmed_allocations.count(),
        'pending_transfers_count': pending_transfers.count(),
        'ineligible_count': ineligible_applications.count(),
        'unallocated_students': unallocated_students[:10], # Show top 10 preview
        'unconfirmed_allocations': unconfirmed_allocations,
        'pending_transfers': pending_transfers,
        'confirmed_allocations': confirmed_allocations,
        'ineligible_applications': ineligible_applications,
    }
    return render(request, 'officer/dashboard.html', context)

@csrf_exempt
def execute_allocations(request):
    if request.method == 'POST':
        try:
            allocated_count = run_allocation_engine()
            messages.success(request, f"Allocation engine executed successfully! {allocated_count} student(s) allocated rooms.")
        except Exception as e:
            messages.error(request, f"Error running allocation engine: {str(e)}")
            
    return redirect('officer_dashboard')

@transaction.atomic
def reset_system_data(request):
    if request.method == 'POST':
        try:
            # 1. Clear transactional accommodation records first
            Allocation.objects.all().delete()
            Application.objects.all().delete()
            TransferRequest.objects.all().delete()
            WaitingList.objects.all().delete()
            MaintenanceLog.objects.all().delete()
            
            # 2. Clear master records (Rooms, Halls, and Students)
            Room.objects.all().delete()
            Hall.objects.all().delete()
            Student.objects.all().delete()
            
            messages.success(request, "Complete database reset successful! All halls, rooms, students, and records have been wiped clean for a fresh start.")
        except Exception as e:
            messages.error(request, f"Error during complete system reset: {str(e)}")
            
    return redirect('officer_dashboard')

@transaction.atomic
def approve_transfer(request, request_id):
    if request.method == 'POST':
        transfer_req = get_object_or_404(TransferRequest, request_id=request_id)
        student = transfer_req.student

        # 1. Enforce validation: Student must have an active confirmed allocation to swap from
        current_alloc = Allocation.objects.filter(
            application__student=student, 
            status='Confirmed'
        ).first()

        if not current_alloc:
            messages.error(request, f"Cannot approve transfer: {student.full_name} does not have an active confirmed allocation to transfer from.")
            return redirect('view_transfers')

        # 2. Find available room matching the requested hall/preference while respecting gender policy
        candidate_rooms = Room.objects.filter(
            hall__hall_name__icontains=transfer_req.requested_preference,
            hall__gender_policy__in=[student.gender, 'Mixed'],
            occupancy_status='Available'
        )

        # Fallback search: look for any available room matching student's gender policy if preference isn't open
        if not candidate_rooms.exists():
            candidate_rooms = Room.objects.filter(
                hall__gender_policy__in=[student.gender, 'Mixed'],
                occupancy_status='Available'
            )

        new_room = candidate_rooms.first()

        if new_room:
            old_room = current_alloc.room
            
            # 3. Free up the old room space
            if old_room:
                old_room.occupancy_status = 'Available'
                old_room.save()

            # 4. Reassign student allocation to new room
            current_alloc.room = new_room
            current_alloc.save()

            # 5. Mark new room as Occupied
            new_room.occupancy_status = 'Occupied'
            new_room.save()

            # 6. Update transfer request status
            transfer_req.status = 'Approved'
            transfer_req.save()

            messages.success(request, f"Transfer request for {student.full_name} approved! Moved from {old_room.hall.hall_name} Room {old_room.room_number} to {new_room.hall.hall_name} Room {new_room.room_number}.")
        else:
            messages.error(request, f"Cannot approve transfer: No available rooms found matching gender policy/preference '{transfer_req.requested_preference}'.")

    return redirect('view_transfers')


def reject_transfer(request, request_id):
    if request.method == 'POST':
        transfer_req = get_object_or_404(TransferRequest, request_id=request_id)
        transfer_req.status = 'Rejected'
        transfer_req.save()

        messages.success(request, f"Transfer request for {transfer_req.student.full_name} has been rejected.")

    return redirect('view_transfers')

def view_transfers(request):
    # Fetch filter & search parameters for transfer management view
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('q', '').strip()

    transfers = TransferRequest.objects.select_related('student').all().order_by('-request_id')

    if status_filter:
        transfers = transfers.filter(status=status_filter)

    if search_query:
        transfers = transfers.filter(
            student__reg_number__icontains=search_query
        ) | transfers.filter(
            student__full_name__icontains=search_query
        )

    context = {
        'transfers': transfers,
        'selected_status': status_filter,
        'search_query': search_query,
        'total_transfers_count': transfers.count(),
    }
    return render(request, 'officer/transfers.html', context)

def view_applications(request):
    # Fetch filter & search parameters
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('q', '').strip()

    applications = Application.objects.select_related(
        'student', 
        'preferred_roommate'
    ).all().order_by('-submission_date')

    if status_filter:
        applications = applications.filter(status=status_filter)

    if search_query:
        applications = applications.filter(student__reg_number__icontains=search_query) | \
                       applications.filter(student__full_name__icontains=search_query)

    context = {
        'applications': applications,
        'selected_status': status_filter,
        'search_query': search_query,
        'total_applications_count': applications.count(),
    }
    return render(request, 'officer/applications.html', context)

def view_waiting_list(request):
    search_query = request.GET.get('q', '').strip()
    gender_filter = request.GET.get('gender', '')

    # Order by priority score descending (highest priority first), then entry timestamp
    waitlist = WaitingList.objects.select_related('student').all().order_by('-priority_score', 'entry_timestamp')

    if gender_filter:
        waitlist = waitlist.filter(student__gender=gender_filter)

    if search_query:
        waitlist = waitlist.filter(
            student__reg_number__icontains=search_query
        ) | waitlist.filter(
            student__full_name__icontains=search_query
        )

    context = {
        'waitlist': waitlist,
        'search_query': search_query,
        'selected_gender': gender_filter,
        'total_waiting_count': waitlist.count(),
        'male_waiting_count': waitlist.filter(student__gender='Male').count(),
        'female_waiting_count': waitlist.filter(student__gender='Female').count(),
    }
    return render(request, 'officer/waiting_list.html', context)


@transaction.atomic
def promote_from_waitlist(request, waitlist_id):
    if request.method == 'POST':
        wait_item = get_object_or_404(WaitingList, queue_id=waitlist_id)
        student = wait_item.student

        # Check if student already has an active application
        app = Application.objects.filter(
            student=student
        ).filter(
            Q(status__iexact='Submitted') | Q(status__iexact='WAITLISTED') | Q(status__iexact='Approved')
        ).first()

        if not app:
            app = Application.objects.create(
                student=student,
                status='APPROVED'
            )

        # Dynamically check rooms with at least 1 free bed matching gender policy
        candidate_rooms = Room.objects.annotate(
            active_count=Count(
                'allocation',
                filter=Q(allocation__status__in=['Pending', 'Confirmed', 'Active'])
            )
        ).filter(
            active_count__lt=F('bed_capacity'),
            hall__gender_policy__iexact=student.gender.strip()
        ) | Room.objects.annotate(
            active_count=Count(
                'allocation',
                filter=Q(allocation__status__in=['Pending', 'Confirmed', 'Active'])
            )
        ).filter(
            active_count__lt=F('bed_capacity'),
            hall__gender_policy__iexact='Mixed'
        )

        # Exclude rooms housing opposite-gender occupants
        opposite_gender = 'Female' if student.gender.casefold() == 'male' else 'Male'
        conflicting_room_ids = Allocation.objects.filter(
            status__in=['Pending', 'Confirmed', 'Active'],
            application__student__gender__iexact=opposite_gender
        ).values_list('room_id', flat=True)

        candidate_rooms = candidate_rooms.exclude(room_id__in=conflicting_room_ids)
        assigned_room = candidate_rooms.first()

        if assigned_room:
            deadline = timezone.now() + timedelta(days=7)
            
            # Create Allocation record
            Allocation.objects.create(
                application=app,
                room=assigned_room,
                confirmation_deadline=deadline,
                status='Pending'
            )
            
            app.status = 'APPROVED'
            app.save()

            # Update room status if full
            current_occupants = Allocation.objects.filter(
                room=assigned_room,
                status__in=['Pending', 'Confirmed', 'Active']
            ).count()
            if current_occupants >= assigned_room.bed_capacity:
                assigned_room.occupancy_status = 'Occupied'
                assigned_room.save()

            # ✨ Automatically Trigger Portal Notification for Student
            Notification.objects.create(
                student=student,
                title="🎉 Room Assigned from Waiting List!",
                message=f"You have been successfully promoted from the waiting list! You are assigned to {assigned_room.hall.hall_name}, Room {assigned_room.room_number}. Please confirm your allocation before the deadline: {deadline.strftime('%b %d, %Y %H:%M')}."
            )

            # Remove student from waitlist
            wait_item.delete()

            messages.success(request, f"Promoted {student.full_name} from waitlist! Assigned to {assigned_room.hall.hall_name} Room {assigned_room.room_number} and notification sent.")
        else:
            messages.error(request, f"Cannot promote {student.full_name}: No available beds matching gender policy '{student.gender}' without room-gender conflicts.")

    return redirect(request.META.get('HTTP_REFERER', 'officer_dashboard'))


@transaction.atomic
def remove_from_waitlist(request, waitlist_id):
    if request.method == 'POST':
        wait_item = get_object_or_404(WaitingList, queue_id=waitlist_id)
        student = wait_item.student
        student_name = student.full_name

        # 1. Update application status to REMOVED so student portal reflects the change
        app = Application.objects.filter(student=student).first()
        if app:
            app.status = 'REMOVED'
            app.save()

        # 2. Automatically dispatch notification to student portal
        Notification.objects.create(
            student=student,
            title="❌ Removed from Waiting List",
            message="Your application has been removed from the official hostel waiting list by the accommodation office. Please contact support for further inquiries."
        )

        # 3. Delete waitlist queue entry
        wait_item.delete()

        messages.success(request, f"Removed {student_name} from the waiting list, updated application status, and notified student.")

    return redirect(request.META.get('HTTP_REFERER', 'officer_dashboard'))

def room_occupancy_inspector(request):
    halls = Hall.objects.all()
    selected_hall_id = request.GET.get('hall', '')

    # Filter rooms by selected hall if provided
    rooms = Room.objects.select_related('hall').all()
    if selected_hall_id:
        rooms = rooms.filter(hall_id=selected_hall_id)

    # Build room details with current occupants
    inspector_data = []
    for room in rooms:
        # Get active or confirmed occupants for this room
        occupants = Allocation.objects.filter(
            room=room,
            status__in=['Confirmed', 'Active']
        ).select_related('application__student')

        occupied_count = occupants.count()
        available_beds = max(0, room.bed_capacity - occupied_count)

        if available_beds == 0:
            room_state = 'Full 🔴'
        elif occupied_count > 0:
            room_state = 'Partially Occupied 🟡'
        else:
            room_state = 'Available 🟢'

        inspector_data.append({
            'room': room,
            'occupants': occupants,
            'occupied_count': occupied_count,
            'available_beds': available_beds,
            'room_state': room_state,
        })

    context = {
        'halls': halls,
        'selected_hall_id': selected_hall_id,
        'inspector_data': inspector_data,
        'total_rooms_inspected': rooms.count(),
    }
    return render(request, 'officer/occupancy_inspector.html', context)

def view_reports(request):
    reports = OccupancyReport.objects.select_related('officer').all().order_by('-report_id')

    context = {
        'reports': reports,
        'total_reports': reports.count(),
    }
    return render(request, 'officer/reports.html', context)

@transaction.atomic
def generate_occupancy_report(request):
    if request.method == 'POST':
        semester = request.POST.get('semester', '2025/2026 Academic Year - Semester 2')
        
        # 1. Automatically calculate free rooms
        total_rooms = Room.objects.count()
        occupied_rooms = Room.objects.filter(occupancy_status='Occupied').count()
        free_rooms_count = max(0, total_rooms - occupied_rooms)

        # 2. Automatically calculate unallocated students with submitted applications
        allocated_student_ids = Allocation.objects.filter(status__in=['Pending', 'Confirmed', 'Active']).values_list('application__student', flat=True)
        unallocated_count = Student.objects.filter(application__isnull=False).exclude(student_id__in=allocated_student_ids).count()

        # 3. Compile penalty/damage summary from Maintenance Logs
        maintenance_logs = MaintenanceLog.objects.all()
        total_penalties = sum(log.damage_penalty_amount for log in maintenance_logs)
        open_issues = maintenance_logs.filter(repair_status='Open').count()
        
        penalty_summary = f"Total Open Maintenance Issues: {open_issues}. Cumulative Damage Penalties Assessed: KES {total_penalties:,.2f}"

        # 4. Assign report to the first available officer session (or create a default one)
        officer = AccommodationOfficer.objects.first()
        if not officer:
            officer = AccommodationOfficer.objects.create(
                staff_credentials='KSU/OFFICER/001',
                department='Main Campus Accommodation'
            )

        # 5. Save the new Occupancy Report record
        OccupancyReport.objects.create(
            officer=officer,
            semester=semester,
            free_rooms_count=free_rooms_count,
            unallocated_students_count=unallocated_count,
            penalty_summary=penalty_summary
        )

        messages.success(request, f"New occupancy report for '{semester}' generated successfully!")
    
    return redirect('view_reports')

def manage_students(request):
    search_query = request.GET.get('q', '').strip()
    gender_filter = request.GET.get('gender', '')
    year_filter = request.GET.get('year', '')
    fee_filter = request.GET.get('fee', '')

    students = Student.objects.all().order_by('full_name')

    # Apply filters
    if gender_filter:
        students = students.filter(gender=gender_filter)
    if year_filter:
        students = students.filter(year_of_study=year_filter)
    if fee_filter == 'cleared':
        students = students.filter(fee_clearance=True)
    elif fee_filter == 'pending':
        students = students.filter(fee_clearance=False)

    # Search by Reg Number or Name
    if search_query:
        students = students.filter(
            reg_number__icontains=search_query
        ) | students.filter(
            full_name__icontains=search_query
        )

    context = {
        'students': students,
        'search_query': search_query,
        'selected_gender': gender_filter,
        'selected_year': year_filter,
        'selected_fee': fee_filter,
        'total_students_count': Student.objects.count(),
        'cleared_count': Student.objects.filter(fee_clearance=True).count(),
        'disciplinary_count': Student.objects.filter(disciplinary_status=True).count(),
    }
    return render(request, 'officer/manage_students.html', context)

def occupancy_analytics(request):
    # 1. Hall Popularity & Allocation Distribution
    hall_stats = Hall.objects.annotate(
        allocated_beds=Count('room__allocation')
    ).values('hall_name', 'allocated_beds', 'total_capacity', 'gender_policy')

    hall_labels = [h['hall_name'] for h in hall_stats]
    allocated_data = [h['allocated_beds'] for h in hall_stats]
    capacity_data = [h['total_capacity'] for h in hall_stats]

    # 2. Room Occupancy Status Breakdowns
    total_rooms = Room.objects.count()
    occupied_rooms = Room.objects.filter(occupancy_status='Occupied').count()
    available_rooms = max(0, total_rooms - occupied_rooms)

    context = {
        'total_rooms': total_rooms,
        'occupied_rooms': occupied_rooms,
        'available_rooms': available_rooms,
        'hall_labels': json.dumps(hall_labels),
        'allocated_data': json.dumps(allocated_data),
        'capacity_data': json.dumps(capacity_data),
        'hall_stats': hall_stats,
    }
    return render(request, 'officer/analytics.html', context)

def view_maintenance_logs(request):
    logs = MaintenanceLog.objects.select_related('room', 'room__hall').all().order_by('-reported_date')
    
    # Calculate total unresolved penalties across the university
    total_penalties = sum(log.damage_penalty_amount for log in logs if log.repair_status != 'Closed')
    open_issues_count = logs.exclude(repair_status='Closed').count()

    context = {
        'logs': logs,
        'total_penalties': total_penalties,
        'open_issues_count': open_issues_count,
    }
    return render(request, 'officer/maintenance_logs.html', context)

@transaction.atomic
def update_maintenance_status(request, log_id):
    log = get_object_or_404(MaintenanceLog, pk=log_id)
    if request.method == 'POST':
        new_status = request.POST.get('repair_status')
        penalty_amount = request.POST.get('damage_penalty_amount')

        if new_status:
            log.repair_status = new_status
        if penalty_amount:
            log.damage_penalty_amount = float(penalty_amount)
        
        log.save()
        messages.success(request, f"Maintenance Log #{log.log_id} updated successfully.")
    
    return redirect('view_maintenance_logs')

def broadcast_notifications(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        message_text = request.POST.get('message')
        target_group = request.POST.get('target_group') # e.g., 'all', 'year_1', 'year_2', 'year_3', 'year_4', 'unallocated'

        # Determine target student cohort
        students = Student.objects.all()
        if target_group == 'year_1':
            students = students.filter(year_of_study=1)
        elif target_group == 'year_2':
            students = students.filter(year_of_study=2)
        elif target_group == 'year_3':
            students = students.filter(year_of_study=3)
        elif target_group == 'year_4':
            students = students.filter(year_of_study=4)
        elif target_group == 'unallocated':
            # Students with submitted applications but without active allocations
            allocated_student_ids = Allocation.objects.filter(status__in=['Active', 'Confirmed']).values_list('application__student_id', flat=True)
            students = students.filter(applications__isnull=False).exclude(student_id__in=allocated_student_ids)

        count = students.count()
        if count > 0:
            notifications = [
                Notification(student=student, title=title, message=message_text)
                for student in students
            ]
            Notification.objects.bulk_create(notifications)
            messages.success(request, f"Successfully broadcasted notification to {count} student(s) under group: {target_group.replace('_', ' ').title()}.")
        else:
            messages.warning(request, "No students matched the selected target cohort.")

        return redirect('broadcast_notifications')

    context = {
        'total_students': Student.objects.count(),
    }
    return render(request, 'officer/broadcast.html', context)

def digital_clearance_pass(request, allocation_id):
    allocation = get_object_or_404(Allocation, pk=allocation_id)
    student = allocation.application.student

    # Construct verification payload for the QR code
    qr_data = (
        f"KISII UNIVERSITY HOSTEL PASS\n"
        f"Reg No: {student.reg_number}\n"
        f"Name: {student.full_name}\n"
        f"Hall: {allocation.room.hall.hall_name}\n"
        f"Room: {allocation.room.room_number}\n"
        f"Status: Confirmed & Cleared"
    )

    # Generate QR Code image in memory
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    context = {
        'allocation': allocation,
        'student': student,
        'qr_code': qr_base64,
    }
    return render(request, 'officer/clearance_pass.html', context)

def gate_audit_trail(request):
    logs = GateLog.objects.select_related('student', 'allocation__room__hall').all().order_by('-timestamp')[:50]
    
    if request.method == 'POST':
        reg_number = request.POST.get('reg_number')
        scan_type = request.POST.get('scan_type') # ENTRY or EXIT
        
        try:
            student = Student.objects.get(reg_number=reg_number)
            # Find active or confirmed room allocation
            active_allocation = Allocation.objects.filter(
                application__student=student, 
                status__in=['Active', 'Confirmed']
            ).first()
            
            if active_allocation:
                GateLog.objects.create(
                    student=student,
                    allocation=active_allocation,
                    scan_type=scan_type
                )
                messages.success(request, f"Gate scan recorded: {student.full_name} ({scan_type}).")
            else:
                messages.error(request, f"Access Denied: Student {reg_number} has no active room allocation!")
        except Student.DoesNotExist:
            messages.error(request, f"Student with registration number {reg_number} not found.")
            
        return redirect('gate_audit_trail')

    context = {
        'logs': logs,
    }
    return render(request, 'officer/gate_logs.html', context)
@transaction.atomic
def remove_from_waitlist(request, waitlist_id):
    if request.method == 'POST':
        # Use pk=waitlist_id to safely fetch the record regardless of custom primary key naming
        wait_item = get_object_or_404(WaitingList, pk=waitlist_id)
        student = wait_item.student
        student_name = student.full_name

        # 1. Update application status to REMOVED so student portal reflects the change
        app = Application.objects.filter(student=student).first()
        if app:
            app.status = 'REMOVED'
            app.save()

        # 2. Automatically dispatch notification to student portal
        Notification.objects.create(
            student=student,
            title="❌ Removed from Waiting List",
            message="Your application has been removed from the official hostel waiting list by the accommodation office. Please contact support for further inquiries."
        )

        # 3. Delete the specific waitlist queue entry & any potential duplicates
        WaitingList.objects.filter(student=student).delete()

        messages.success(request, f"Removed {student_name} from the waiting list, updated application status, and notified student.")

    return redirect(request.META.get('HTTP_REFERER', 'officer_dashboard'))
@transaction.atomic
def clear_ineligible_application(request, application_id):
    if request.method == 'POST':
        app = get_object_or_404(Application, pk=application_id)
        student = app.student

        # Set status to 'DRAFT' so it does NOT inflate the unallocated count
        # until the student explicitly re-submits from their portal.
        app.status = 'DRAFT'
        if hasattr(app, 'ineligibility_reason'):
            app.ineligibility_reason = None
        app.save()

        # Send notification to student portal that eligibility has been cleared/reviewed
        Notification.objects.create(
            student=student,
            title="✅ Application Status Cleared",
            message="Your hostel application ineligibility has been cleared by the accommodation office. Please review and re-submit your application."
        )

        messages.success(request, f"Cleared ineligible status for {student.full_name}. Application moved to draft status pending student re-submission.")

    return redirect(request.META.get('HTTP_REFERER', 'view_applications'))