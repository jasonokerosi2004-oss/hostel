from django import forms
from .models import Student, TransferRequest, Application, Hall, Room

class StudentProfileForm(forms.ModelForm):
    year_of_study = forms.TypedChoiceField(
        choices=[(1, 'Year 1'), (2, 'Year 2'), (3, 'Year 3'), (4, 'Year 4')],
        coerce=int,
        widget=forms.Select(attrs={
            'class': 'form-control',
            'style': 'width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; background-color: #fff;'
        })
    )

    gender = forms.ChoiceField(
        choices=[('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')],
        widget=forms.Select(attrs={
            'class': 'form-control',
            'style': 'width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; background-color: #fff;'
        })
    )

    class Meta:
        model = Student
        fields = ['full_name', 'reg_number', 'year_of_study', 'gender', 'home_distance', 'profile_picture']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'style': 'width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; background-color: #fff;'
            }),
            'reg_number': forms.TextInput(attrs={
                'class': 'form-control',
                'style': 'width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; background-color: #fff;'
            }),
            'home_distance': forms.NumberInput(attrs={
                'class': 'form-control',
                'style': 'width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; background-color: #fff;'
            }),
            'profile_picture': forms.FileInput(attrs={
                'class': 'form-control',
                'style': 'width: 100%; padding: 6px; border: 1px solid #ccc; border-radius: 4px; background-color: #fff;'
            }),
        }
        labels = {
            'full_name': 'Full Name',
            'reg_number': 'Registration Number',
            'home_distance': 'Home Distance (km)',
            'profile_picture': 'Profile Picture',
        }


class TransferRequestForm(forms.ModelForm):
    class Meta:
        model = TransferRequest
        fields = ['requested_preference', 'reason']
        widgets = {
            'requested_preference': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter preferred hall or room (e.g., Room 4, JUPITER)',
                'style': 'width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; background-color: #fff;'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 4, 
                'placeholder': 'Please state the reason for your transfer request (e.g., medical reasons, roommate issues, etc.)',
                'style': 'width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; background-color: #fff;'
            }),
        }


class RoomApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ['preferred_hall', 'preferred_room_type', 'preferred_roommate']

    def __init__(self, *args, **kwargs):
        current_student = kwargs.pop('current_student', None)
        super().__init__(*args, **kwargs)
        
        # Dynamically load ALL registered halls and their specific rooms from the database
        room_choices = [('', '--- Select Preferred Hall or Specific Room ---')]
        
        for hall in Hall.objects.all():
            # 1. Add the Hall as a main selectable option
            hall_label = f"🏢 Hall: {hall.hall_name} — Policy: {hall.gender_policy} (Capacity: {hall.total_capacity})"
            room_choices.append((hall.hall_name, hall_label))
            
            # 2. Add individual rooms belonging to this hall underneath
            hall_rooms = Room.objects.filter(hall=hall)
            for r in hall_rooms:
                room_value = f"Hall: {hall.hall_name} - Room {r.room_number}"
                room_display = f"   └─ Room {r.room_number} ({r.room_type}) [Status: {r.occupancy_status}]"
                room_choices.append((room_value, room_display))
            
        self.fields['preferred_hall'] = forms.ChoiceField(
            choices=room_choices,
            widget=forms.Select(attrs={
                'class': 'form-control',
                'style': 'width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; background-color: #fff;'
            })
        )
        
        # Preferred Room Type choices (backup preference)
        room_type_choices = [
            ('', '--- Select Room Type Preference ---'),
            ('Single', 'Single Room (1 Bed)'),
            ('Double', 'Double Room (2 Beds)'),
            ('Triple', 'Triple Room (3 Beds)'),
        ]
        self.fields['preferred_room_type'] = forms.ChoiceField(
            choices=room_type_choices,
            required=False,
            widget=forms.Select(attrs={
                'class': 'form-control',
                'style': 'width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; background-color: #fff;'
            })
        )
        
        # Populate preferred roommate dropdown (ForeignKey to Student, excluding self)
        if current_student:
            self.fields['preferred_roommate'].queryset = Student.objects.exclude(pk=current_student.pk)
        else:
            self.fields['preferred_roommate'].queryset = Student.objects.all()
            
        self.fields['preferred_roommate'].required = False
        self.fields['preferred_roommate'].empty_label = "None (No Roommate Preference)"
        self.fields['preferred_roommate'].widget.attrs.update({
            'class': 'form-control',
            'style': 'width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; background-color: #fff;'
        })
        
        # Field Labels
        self.fields['preferred_hall'].label = 'Preferred Hall / Specific Room'
        self.fields['preferred_room_type'].label = 'Preferred Room Type (Optional Backup)'
        self.fields['preferred_roommate'].label = 'Preferred Roommate (Optional)'