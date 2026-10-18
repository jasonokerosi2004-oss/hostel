from django.contrib import admin, messages
from .models import (
    Hall, Room, Student, Application, Caretaker, 
    AccommodationOfficer, Allocation, WaitingList, 
    TransferRequest, MaintenanceLog, OccupancyReport,Announcement,Notification
)
from .services import run_allocation_engine

# Register other core models (Notice Allocation is removed from here)
admin.site.register(Hall)
admin.site.register(Room)
admin.site.register(Student)
admin.site.register(WaitingList)
admin.site.register(Caretaker)
admin.site.register(AccommodationOfficer)
admin.site.register(TransferRequest)
admin.site.register(MaintenanceLog)
admin.site.register(OccupancyReport)
admin.site.register(Notification)
@admin.register(Application)

class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('application_id', 'student', 'preferred_hall', 'status', 'submission_date')
    list_filter = ('status', 'preferred_hall')
    search_fields = ('student__reg_number', 'student__full_name', 'preferred_hall')
    actions = ['run_allocation_action']

    @admin.action(description="🚀 Run Room Allocation Engine")
    def run_allocation_action(self, request, queryset):
        """Custom admin action to trigger the allocation engine"""
        try:
            allocated_count = run_allocation_engine()
            self.message_user(
                request, 
                f"Success! Allocation engine executed. {allocated_count} student(s) successfully allocated rooms.", 
                level=messages.SUCCESS
            )
        except Exception as e:
            self.message_user(
                request, 
                f"Error running allocation engine: {str(e)}", 
                level=messages.ERROR
            )

@admin.register(Allocation)
class AllocationAdmin(admin.ModelAdmin):
    list_display = ('allocation_id', 'application', 'room', 'timestamp', 'status')
    list_filter = ('room__hall', 'status', 'timestamp')
    search_fields = ('application__student__reg_number', 'application__student__full_name', 'room__room_number')

from django.contrib import admin
from .models import Announcement, Student

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('title', 'message')