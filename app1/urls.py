from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views
from . import views
urlpatterns = [
    
    path('', views.home, name='home'),
    path('register_employee/', views.register_employee, name='register_employee'),
    path('register-success/', views.register_success, name='register_success'),
    path('capture-and-recognize/', views.capture_and_recognize, name='capture_and_recognize'),
    path('attendance_list/', views.emp_attendance_list, name='emp_attendance_list'),
    path('employee_list/', views.employee_list, name='employee-list'),
    path('emp_detail/<int:pk>/', views.emp_detail, name='emp-detail'),
    path('emp_authorize/<int:pk>/authorize/', views.emp_authorize, name='emp-authorize'),
    path('emp_delete/<int:pk>/delete/', views.emp_delete, name='emp-delete'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('camera-config/', views.camera_config_create, name='camera_config_create'),
    path('camera-config/list/', views.camera_config_list, name='camera_config_list'),
    path('camera-config/update/<int:pk>/', views.camera_config_update, name='camera_config_update'),
    path('camera-config/delete/<int:pk>/', views.camera_config_delete, name='camera_config_delete'),
]
    

