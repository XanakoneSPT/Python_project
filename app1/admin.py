from django.contrib import admin
from .models import Employee, Attendance, CameraConfiguration


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = [
        'employee_id', 
        'name', 
        'email', 
        'phone_number', 
        'designation', 
        'department', 
        'is_active'
    ]
    list_filter = ['department', 'is_active']
    search_fields = ['name', 'email', 'employee_id']
    ordering = ['employee_id']  # Orders by employee ID


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['employee', 'date', 'check_in_time', 'check_out_time']
    list_filter = ['date']
    search_fields = ['employee__name', 'employee__employee_id']

    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing an existing object
            return ['employee', 'date', 'check_in_time', 'check_out_time']
        return ['date', 'check_in_time', 'check_out_time']  # Adding a new object

    def save_model(self, request, obj, form, change):
        if change:  # Editing an existing object
            # Ensure check-in and check-out times cannot be modified via admin
            original = Attendance.objects.get(id=obj.id)
            obj.check_in_time = original.check_in_time
            obj.check_out_time = original.check_out_time
        super().save_model(request, obj, form, change)


@admin.register(CameraConfiguration)
class CameraConfigurationAdmin(admin.ModelAdmin):
    list_display = ['name', 'camera_source', 'threshold']
    search_fields = ['name']
