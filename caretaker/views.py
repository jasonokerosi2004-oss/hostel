from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from student.models import Caretaker, Allocation, CheckInLog, MaintenanceLog, Room, Hall, GateLog, Student, RoomInspection

@login_required
def caretaker_dashboard(request):
    hall = Hall.objects.first()
    if not hall:
        return render(request, 'caretaker/dashboard.html', {'error': 'No halls found in the database. Please create a Hall in Django Admin first.'})

    caretaker, created = Caretaker.objects.get_or_create(
        user=request.user,
        defaults={
            'name': request.user.username if request.user.username else 'Caretaker',
            'hall': hall,
            'contact_info': '0700000000'
        }
    )
    assigned_hall = caretaker.hall

    hall_allocations = Allocation.objects.filter(room__hall=assigned_hall, status='Confirmed')
    hall_checkins = CheckInLog.objects.filter(allocation__room__hall=assigned_hall)
    checked_in_allocation_ids = hall_checkins.values_list('allocation_id', flat=True)

    pending_checkins = hall_allocations.exclude(pk__in=checked_in_allocation_ids)
    completed_checkins = hall_checkins.select_related('allocation__student', 'allocation__room')
    
    # Active residents currently residing in the hall
    active_residents = Allocation.objects.filter(room__hall=assigned_hall, status='Active')

    open_repairs = MaintenanceLog.objects.filter(room__hall=assigned_hall, repair_status='Open')

    context = {
        'caretaker': caretaker,
        'assigned_hall': assigned_hall,
        'pending_checkins': pending_checkins,
        'completed_checkins': completed_checkins,
        'active_residents': active_residents,
        'open_repairs': open_repairs,
    }
    return render(request, 'caretaker/dashboard.html', context)


@login_required
def process_physical_checkin(request, allocation_id):
    hall = Hall.objects.first()
    caretaker, created = Caretaker.objects.get_or_create(
        user=request.user,
        defaults={
            'name': request.user.username if request.user.username else 'Caretaker',
            'hall': hall,
            'contact_info': '0700000000'
        }
    )
    allocation = get_object_or_404(Allocation, pk=allocation_id, room__hall=caretaker.hall)
    
    checkin, created = CheckInLog.objects.get_or_create(allocation=allocation)
    
    if request.method == 'POST':
        checkin.key_issued = request.POST.get('key_issued') == 'on'
        checkin.inventory_verified = request.POST.get('inventory_verified') == 'on'
        checkin.notes = request.POST.get('notes', '')
        checkin.save()
        
        # Update allocation status to Active once checked in
        allocation.status = 'Active'
        allocation.save()
        
        return redirect('caretaker_dashboard')
        
    context = {
        'allocation': allocation,
        'checkin': checkin,
    }
    return render(request, 'caretaker/checkin.html', context)


@login_required
def log_room_defect(request):
    hall = Hall.objects.first()
    caretaker, created = Caretaker.objects.get_or_create(
        user=request.user,
        defaults={
            'name': request.user.username if request.user.username else 'Caretaker',
            'hall': hall,
            'contact_info': '0700000000'
        }
    )
    hall_rooms = Room.objects.filter(hall=caretaker.hall)

    if request.method == 'POST':
        room_id = request.POST.get('room_id')
        description = request.POST.get('description')
        severity = request.POST.get('severity', 'Medium')
        
        room = get_object_or_404(Room, pk=room_id, hall=caretaker.hall)
        MaintenanceLog.objects.create(
            room=room,
            description=description,
            severity=severity,
            repair_status='Open'
        )
        return redirect('caretaker_dashboard')

    context = {
        'hall_rooms': hall_rooms,
    }
    return render(request, 'caretaker/log_defect.html', context)


@login_required
def gate_scanner(request):
    hall = Hall.objects.first()
    caretaker, created = Caretaker.objects.get_or_create(
        user=request.user,
        defaults={
            'name': request.user.username if request.user.username else 'Caretaker',
            'hall': hall,
            'contact_info': '0700000000'
        }
    )
    
    message = None
    error = None
    
    if request.method == 'POST':
        reg_number = request.POST.get('reg_number', '').strip()
        scan_type = request.POST.get('scan_type', 'ENTRY')
        
        try:
            student = Student.objects.get(reg_number=reg_number)
            allocation = Allocation.objects.filter(student=student, room__hall=caretaker.hall).first()
            
            if not allocation:
                error = f"Student {reg_number} is not allocated to a room in your assigned hall ({caretaker.hall.hall_name})."
            else:
                GateLog.objects.create(
                    student=student,
                    allocation=allocation,
                    scan_type=scan_type,
                    gate_name=f"{caretaker.hall.hall_name} Main Gate"
                )
                message = f"Successfully recorded {scan_type} scan for {student.full_name} ({student.reg_number})."
        except Student.DoesNotExist:
            error = f"Student with Registration Number '{reg_number}' not found in the system."

    recent_scans = GateLog.objects.filter(allocation__room__hall=caretaker.hall).order_by('-timestamp')[:10]
    
    context = {
        'recent_scans': recent_scans,
        'message': message,
        'error': error,
        'caretaker': caretaker,
    }
    return render(request, 'caretaker/scanner.html', context)


@login_required
def process_checkout(request, allocation_id):
    hall = Hall.objects.first()
    caretaker, created = Caretaker.objects.get_or_create(
        user=request.user,
        defaults={
            'name': request.user.username if request.user.username else 'Caretaker',
            'hall': hall,
            'contact_info': '0700000000'
        }
    )
    allocation = get_object_or_404(Allocation, pk=allocation_id, room__hall=caretaker.hall)
    
    if request.method == 'POST':
        key_returned = request.POST.get('key_returned') == 'on'
        damage_penalty = request.POST.get('damage_penalty', '0.00')
        penalty_reason = request.POST.get('penalty_reason', '')
        
        allocation.status = 'Checked Out'
        allocation.save()
        
        return redirect('caretaker_dashboard')
        
    context = {
        'allocation': allocation,
    }
    return render(request, 'caretaker/checkout.html', context)


@login_required
def hall_room_list(request):
    hall = Hall.objects.first()
    caretaker, created = Caretaker.objects.get_or_create(
        user=request.user,
        defaults={
            'name': request.user.username if request.user.username else 'Caretaker',
            'hall': hall,
            'contact_info': '0700000000'
        }
    )
    assigned_hall = caretaker.hall

    rooms = Room.objects.filter(hall=assigned_hall).prefetch_related('allocation_set', 'maintenancelog_set')

    room_data = []
    for room in rooms:
        # Include both Active and Confirmed allocations so students assigned yesterday show up correctly
        allocated_students = room.allocation_set.filter(status__in=['Active', 'Confirmed'])
        open_maintenance = room.maintenancelog_set.filter(repair_status='Open')
        
        room_capacity = room.bed_capacity
        
        if open_maintenance.exists():
            status = 'Under Maintenance'
            status_bg = 'bg-danger'
        elif allocated_students.count() >= room_capacity:
            status = 'Fully Occupied'
            status_bg = 'bg-secondary'
        elif allocated_students.count() > 0:
            status = 'Partially Occupied'
            status_bg = 'bg-warning text-dark'
        else:
            status = 'Vacant'
            status_bg = 'bg-success'

        room_data.append({
            'room': room,
            'occupants': allocated_students,
            'occupant_count': allocated_students.count(),
            'vacant_beds': room_capacity - allocated_students.count(),
            'open_maintenance_count': open_maintenance.count(),
            'status': status,
            'status_bg': status_bg,
        })

    context = {
        'caretaker': caretaker,
        'assigned_hall': assigned_hall,
        'room_data': room_data,
        'total_rooms': rooms.count(),
    }
    return render(request, 'caretaker/hall_rooms.html', context)
@login_required
def mark_room_under_repair(request, room_id):
    caretaker = get_object_or_404(Caretaker, user=request.user)
    room = get_object_or_404(Room, pk=room_id, hall=caretaker.hall)
    
    room.occupancy_status = 'Under Maintenance'
    room.save()
    
    # Automatically log an open maintenance record if none exists
    if not MaintenanceLog.objects.filter(room=room, repair_status='Open').exists():
        MaintenanceLog.objects.create(
            room=room,
            description="Marked under repair by caretaker.",
            severity='High',
            repair_status='Open'
        )
        
    return redirect('hall_room_list')


@login_required
def return_room_to_service(request, room_id):
    caretaker = get_object_or_404(Caretaker, user=request.user)
    room = get_object_or_404(Room, pk=room_id, hall=caretaker.hall)
    
    room.occupancy_status = 'Available'
    room.save()
    
    # Close open maintenance logs for this room
    MaintenanceLog.objects.filter(room=room, repair_status='Open').update(repair_status='Closed')
    
    return redirect('hall_room_list')


@login_required
def conduct_room_inspection(request, room_id):
    caretaker = get_object_or_404(Caretaker, user=request.user)
    room = get_object_or_404(Room, pk=room_id, hall=caretaker.hall)
    
    if request.method == 'POST':
        furniture = request.POST.get('furniture_rating', 'Good')
        electrical = request.POST.get('electrical_rating', 'Good')
        plumbing = request.POST.get('plumbing_rating', 'Good')
        charges = float(request.POST.get('damage_charges', 0.0))
        remarks = request.POST.get('remarks', '')
        
        RoomInspection.objects.create(
            room=room,
            caretaker=caretaker,
            furniture_rating=furniture,
            electrical_rating=electrical,
            plumbing_rating=plumbing,
            damage_charges=charges,
            remarks=remarks
        )
        
        # If damages resulted in fines, also log a maintenance penalty record
        if charges > 0:
            MaintenanceLog.objects.create(
                room=room,
                description=f"Inspection Damage Fine: {remarks}",
                severity='Severe',
                repair_status='Open',
                damage_penalty_amount=charges
            )
            
        return redirect('hall_room_list')
        
    context = {
        'room': room,
    }
    return render(request, 'caretaker/inspect_room.html', context)