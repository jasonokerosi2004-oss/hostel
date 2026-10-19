from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from .models import Student, Allocation, Room, Announcement, TransferRequest, Application, Notification, WaitingList
from .forms import StudentProfileForm, TransferRequestForm, RoomApplicationForm
from django.contrib.auth.forms import UserCreationForm

@login_required
def student_dashboard(request):
    student = Student.objects.filter(user=request.user).first()
    
    # Fetch student's room allocation
    allocation = Allocation.objects.filter(application__student=student).first() if student else None
    
    # Fetch the student's room application status
    application = Application.objects.filter(student=student).first() if student else None
    
    # Fetch the latest active announcement from the database
    announcement = Announcement.objects.filter(is_active=True).order_by('-created_at').first()

    # STRICT FILTERING: Fetch transfer requests belonging ONLY to the logged-in student
    transfer_requests = TransferRequest.objects.filter(student=student).order_by('-request_id') if student else []

    # STRICT FILTERING: Fetch unread notifications belonging ONLY to the logged-in student
    notifications = Notification.objects.filter(student=student, is_read=False).order_by('-created_at') if student else []

    # ✨ Check if student is on the waiting list and calculate queue position
    waitlist_entry = WaitingList.objects.filter(student=student).first() if student else None
    waitlist_position = None
    if waitlist_entry:
        higher_priority_count = WaitingList.objects.filter(
            priority_score__gt=waitlist_entry.priority_score
        ).count()
        same_score_earlier_count = WaitingList.objects.filter(
            priority_score=waitlist_entry.priority_score,
            entry_timestamp__lt=waitlist_entry.entry_timestamp
        ).count()
        waitlist_position = higher_priority_count + same_score_earlier_count + 1

    if request.method == 'POST':
        form = StudentProfileForm(request.POST, request.FILES, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile details were updated successfully! 🎉")
            return redirect('student_dashboard')
        else:
            messages.error(request, "Please correct the errors in the form below.")
    else:
        form = StudentProfileForm(instance=student)
        if student and student.gender:
            form.initial['gender'] = student.gender.capitalize()

    context = {
        'student': student,
        'allocation': allocation,
        'application': application,
        'form': form,
        'announcement': announcement,
        'transfer_requests': transfer_requests,
        'notifications': notifications,
        'waitlist_entry': waitlist_entry,
        'waitlist_position': waitlist_position,
    }
    return render(request, 'student/dashboard.html', context)


@login_required
def apply_room(request):
    student = Student.objects.filter(user=request.user).first()
    if not student:
        messages.error(request, "Student profile not found.")
        return redirect('student_dashboard')
    
    if not student.fee_clearance:
        messages.error(request, "You must have fee clearance before applying for a room. ❌")
        return redirect('student_dashboard')

    # Check if student already submitted an ACTIVE/PENDING application (exclude REMOVED, INELIGIBLE, DRAFT)
    active_application = Application.objects.filter(student=student).exclude(
        status__in=['REMOVED', 'INELIGIBLE', 'DRAFT', 'REJECTED', 'CANCELLED']
    ).first()
    
    if active_application:
        messages.warning(request, "You already have an active submitted room application.")
        return redirect('student_dashboard')

    # Fetch existing application instance if available (to allow re-submission after removal or draft reset)
    existing_app = Application.objects.filter(student=student).first()

    if request.method == 'POST':
        form = RoomApplicationForm(request.POST, current_student=student, instance=existing_app)
        if form.is_valid():
            app = form.save(commit=False)
            app.student = student
            app.status = 'Submitted'
            if hasattr(app, 'ineligibility_reason'):
                app.ineligibility_reason = None
            app.save()

            # ✨ ROOMMATE PAIRING SYNC: Automatically submit/update roommate application if selected
            if hasattr(app, 'preferred_roommate') and app.preferred_roommate:
                roommate = app.preferred_roommate
                roommate_app, _ = Application.objects.get_or_create(student=roommate)
                roommate_app.status = 'Submitted'
                roommate_app.preferred_hall = app.preferred_hall
                roommate_app.preferred_roommate = student  # Mutual link back
                if hasattr(roommate_app, 'preferred_room_type') and hasattr(app, 'preferred_room_type'):
                    roommate_app.preferred_room_type = app.preferred_room_type
                roommate_app.save()

            messages.success(request, "Hostel accommodation application submitted successfully! 🎉")
            return redirect('student_dashboard')
        else:
            messages.error(request, "Please correct the errors in your application form below.")
    else:
        form = RoomApplicationForm(current_student=student, instance=existing_app)

    context = {
        'form': form,
    }
    return render(request, 'student/apply_room.html', context)


@login_required
def request_transfer(request):
    student = Student.objects.filter(user=request.user).first()
    if not student:
        messages.error(request, "Student profile not found.")
        return redirect('student_dashboard')

    # Ensure the student has an active room allocation before requesting a transfer
    allocation = Allocation.objects.filter(application__student=student).first()
    if not allocation:
        messages.warning(request, "You must have an allocated room before requesting a transfer.")
        return redirect('student_dashboard')

    if request.method == 'POST':
        form = TransferRequestForm(request.POST)
        if form.is_valid():
            transfer = form.save(commit=False)
            transfer.student = student
            transfer.status = 'Submitted'
            transfer.save()
            messages.success(request, "Room transfer request submitted successfully! 📋")
            return redirect('student_dashboard')
        else:
            messages.error(request, "Please check your form input below.")
    else:
        form = TransferRequestForm()

    context = {
        'form': form,
        'allocation': allocation,
    }
    return render(request, 'student/request_transfer.html', context)


@login_required
def confirm_allocation(request):
    student = Student.objects.filter(user=request.user).first()
    if not student:
        messages.error(request, "Student profile not found.")
        return redirect('student_dashboard')

    # Fetch the student's pending room allocation
    allocation = Allocation.objects.filter(
        application__student=student, 
        status__iexact='pending'
    ).first()
    
    if not allocation:
        messages.warning(request, "No pending room allocation found to confirm.")
        return redirect('student_dashboard')

    if request.method == 'POST':
        allocation.status = 'Confirmed'
        allocation.save()

        room = allocation.room
        room.occupancy_status = 'Occupied'
        room.save()

        success_msg = f"Room {room.room_number} allocation confirmed successfully! 🎉"
        storage = messages.get_messages(request)
        existing_messages = {m.message for m in storage}
        storage.used = True

        if success_msg not in existing_messages:
            messages.success(request, success_msg)

        return redirect('student_dashboard')

    context = {
        'allocation': allocation,
    }
    return render(request, 'student/confirm_allocation.html', context)


@login_required
def custom_login_redirect(request):
    user = request.user
    
    if hasattr(user, 'accommodationofficer'):
        return redirect('officer_dashboard')
    elif hasattr(user, 'caretaker'):
        return redirect('caretaker_dashboard')
    elif hasattr(user, 'student'):
        return redirect('student_dashboard')
    elif user.is_staff or user.is_superuser:
        return redirect('admin:index')
    else:
        return redirect('student_dashboard')


@csrf_exempt
def custom_logout_view(request):
    logout(request)
    return redirect('login')

def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Automatically create a linked Student profile if your model requires it
            # Student.objects.get_or_create(user=user)
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created for {username}! You can now log in.')
            return redirect('/accounts/login/')  # Redirects back to your login page
        else:
            messages.error(request, "Please correct the errors in the form below.")
    else:
        form = UserCreationForm()
    
    context = {
        'form': form,
    }
    return render(request, 'student/signup.html', context)