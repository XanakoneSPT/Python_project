import os
import cv2
import numpy as np
import torch
from facenet_pytorch import InceptionResnetV1, MTCNN
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from .models import Employee, Attendance, CameraConfiguration
from django.core.files.base import ContentFile
from datetime import datetime, timedelta
from django.utils import timezone
import pygame  # Import pygame for playing sounds
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
import threading
import time
import base64
from django.db import IntegrityError
from django.contrib.auth.decorators import user_passes_test
from django.utils.timezone import now
import csv
from django.http import HttpResponse
from openpyxl import Workbook



# Initialize MTCNN and InceptionResnetV1
mtcnn = MTCNN(keep_all=True)
resnet = InceptionResnetV1(pretrained='vggface2').eval()

# Function to detect and encode faces
def detect_and_encode(image):
    with torch.no_grad():
        boxes, _ = mtcnn.detect(image)
        if boxes is not None:
            faces = []
            for box in boxes:
                face = image[int(box[1]):int(box[3]), int(box[0]):int(box[2])]
                if face.size == 0:
                    continue
                face = cv2.resize(face, (160, 160))
                face = np.transpose(face, (2, 0, 1)).astype(np.float32) / 255.0
                face_tensor = torch.tensor(face).unsqueeze(0)
                encoding = resnet(face_tensor).detach().numpy().flatten()
                faces.append(encoding)
            return faces
    return []

# Function to encode uploaded images
def encode_uploaded_images():
    known_face_encodings = []
    known_face_names = []

    # Fetch only authorized images
    uploaded_images = Employee.objects.filter(is_active=True)

    for student in uploaded_images:
        image_path = os.path.join(settings.MEDIA_ROOT, str(student.profile_picture.name))
        known_image = cv2.imread(image_path)
        known_image_rgb = cv2.cvtColor(known_image, cv2.COLOR_BGR2RGB)
        encodings = detect_and_encode(known_image_rgb)
        if encodings:
            known_face_encodings.extend(encodings)
            known_face_names.append(student.name)

    return known_face_encodings, known_face_names

# Function to recognize faces
def recognize_faces(known_encodings, known_names, test_encodings, threshold=0.6):
    recognized_names = []
    for test_encoding in test_encodings:
        distances = np.linalg.norm(known_encodings - test_encoding, axis=1)
        min_distance_idx = np.argmin(distances)
        if distances[min_distance_idx] < threshold:
            recognized_names.append(known_names[min_distance_idx])
        else:
            recognized_names.append('Not Recognized')
    return recognized_names

######################################################################
# View for registering an employee
def register_employee(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        employee_id = request.POST.get('employee_id')
        email = request.POST.get('email')
        phone_number = request.POST.get('phone_number')
        designation = request.POST.get('designation')
        department = request.POST.get('department')
        image_data = request.POST.get('image_data')

        # Check for duplicate employee ID
        if Employee.objects.filter(employee_id=employee_id).exists():
            messages.error(request, "An employee with this ID already exists.")
            return render(request, 'register_employee.html')

        # Decode the base64 image data
        profile_picture = None
        if image_data:
            try:
                header, encoded = image_data.split(',', 1)
                profile_picture = ContentFile(base64.b64decode(encoded), name=f"{employee_id}.jpg")
            except Exception as e:
                messages.error(request, "Error decoding image. Please try again.")
                print(f"Error decoding image: {e}")
                return render(request, 'register_employee.html')

        # Create the Employee instance
        employee = Employee(
            employee_id=employee_id,
            name=name,
            email=email,
            phone_number=phone_number,
            designation=designation,
            department=department,
            profile_picture=profile_picture,  # Use profile_picture field
            is_active=True  # Default to True, or customize as needed
        )

        # Save the employee and redirect to a success page
        try:
            employee.save()
            messages.success(request, "Employee registered successfully.")
            return redirect('register_success')  # Redirect to a success page (customize as needed)
        except Exception as e:
            messages.error(request, "An error occurred while registering the employee. Please try again.")
            print(f"Error saving employee: {e}")
            return render(request, 'register_employee.html')

    return render(request, 'register_employee.html')


######################################################################

# Success view after capturing student information and image
def register_success(request):
    return render(request, 'register_success.html')


#####################################################################
def capture_and_recognize(request):
    stop_events = []  # List to store stop events for each thread
    camera_threads = []  # List to store threads for each camera
    camera_windows = []  # List to store window names
    error_messages = []  # List to capture errors from threads
    
    # Create a shared dictionary for status messages
    status_messages = {}

    def process_frame(cam_config, stop_event):
        """Thread function to capture and process frames for each camera."""
        cap = None
        window_created = False  # Flag to track if the window was created
        try:
            # Check if the camera source is a number (local webcam) or a string (IP camera URL)
            if cam_config.camera_source.isdigit():
                cap = cv2.VideoCapture(int(cam_config.camera_source))  # Use integer index for webcam
            else:
                cap = cv2.VideoCapture(cam_config.camera_source)  # Use string for IP camera URL

            if not cap.isOpened():
                raise Exception(f"Unable to access camera {cam_config.name}.")

            # Better resolution for accuracy but not full HD
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 800)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 600)

            threshold = cam_config.threshold

            # Initialize pygame mixer for sound playback
            pygame.mixer.init()
            success_sound = pygame.mixer.Sound('app1/suc.wav')  # Load sound path

            window_name = f'Face Recognition - {cam_config.name}'
            camera_windows.append(window_name)  # Track the window name
            
            # Load known face encodings ONCE at the beginning
            known_face_encodings, known_face_names = encode_uploaded_images()
            
            # Cache to prevent constant recalculation
            face_locations_cache = None
            face_encodings_cache = None
            
            # Variables for frame processing
            frame_count = 0
            skip_frames = 1  # Process more frames for better detection
            recognition_cooldown = {}  # Track recognition cooldown
            
            while not stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    print(f"Failed to capture frame for camera: {cam_config.name}")
                    break  # If frame capture fails, break from the loop

                frame_count += 1
                process_this_frame = frame_count % skip_frames == 0
                
                # Slightly reduce size for processing - less reduction for better accuracy
                if process_this_frame:
                    # Use a factor of 0.75 instead of 0.5 for better detection
                    process_frame = cv2.resize(frame, (0, 0), fx=0.75, fy=0.75)
                    process_frame_rgb = cv2.cvtColor(process_frame, cv2.COLOR_BGR2RGB)
                    
                    # Detect and encode faces
                    face_locations_cache = mtcnn.detect(process_frame_rgb)[0]
                    if face_locations_cache is not None and len(face_locations_cache) > 0:
                        face_encodings_cache = detect_and_encode(process_frame_rgb)
                
                # Process recognition if we have cached faces
                current_time = now()
                if face_locations_cache is not None and face_encodings_cache and len(face_encodings_cache) > 0:
                    # Only do recognition if we have known faces to compare against
                    if known_face_encodings and len(known_face_encodings) > 0:
                        names = recognize_faces(np.array(known_face_encodings), known_face_names, face_encodings_cache, threshold)
                        
                        # Draw boxes and process recognition
                        for i, (name, box) in enumerate(zip(names, face_locations_cache)):
                            if box is not None:
                                # Scale coordinates to the original frame
                                scale_factor = 1 / 0.75
                                (x1, y1, x2, y2) = map(int, [coord * scale_factor for coord in box])
                                
                                # Draw rectangle around face
                                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                cv2.putText(frame, name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2, cv2.LINE_AA)
                                
                                # Handle recognition for identified faces
                                if name != 'Not Recognized':
                                    # Check cooldown to prevent too frequent recognitions
                                    last_recognition = recognition_cooldown.get(name, None)
                                    if last_recognition is None or (current_time - last_recognition).total_seconds() > 2:
                                        recognition_cooldown[name] = current_time
                                        
                                        # Process attendance immediately for faster feedback
                                        status = check_attendance_status(name, current_time, success_sound)
                                        if status:
                                            status_messages[name] = {
                                                'message': status,
                                                'time': current_time,
                                                'color': (0, 255, 0) if 'checked in' in status or 'checked out' in status else (0, 0, 255)
                                            }
                
                # Display status messages for recognized people
                y_offset = 50
                for name, status_info in list(status_messages.items()):
                    # Only show messages for 5 seconds
                    if (current_time - status_info['time']).total_seconds() < 5:
                        cv2.putText(frame, f"{status_info['message']}", (50, y_offset), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.75, status_info['color'], 2, cv2.LINE_AA)
                        y_offset += 30
                    else:
                        # Remove old messages
                        status_messages.pop(name, None)

                # Display frame
                if not window_created:
                    cv2.namedWindow(window_name)  # Only create window once
                    window_created = True  # Mark window as created

                cv2.imshow(window_name, frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    stop_event.set()  # Signal the thread to stop when 'q' is pressed
                    break

        except Exception as e:
            print(f"Error in thread for {cam_config.name}: {e}")
            error_messages.append(str(e))  # Capture error message
        finally:
            if cap is not None:
                cap.release()
            if window_created:
                cv2.destroyWindow(window_name)  # Only destroy if window was created

    def check_attendance_status(name, current_time, success_sound):
        """Check attendance status and return appropriate message."""
        try:
            employees = Employee.objects.filter(name=name)
            if employees.exists():
                employee = employees.first()

                # Manage attendance based on check-in and check-out logic
                attendance, created = Attendance.objects.get_or_create(employee=employee, date=current_time.date())
                
                if created:
                    attendance.mark_check_in()
                    success_sound.play()
                    return f"{name}, checked in"
                else:
                    if attendance.check_in_time and not attendance.check_out_time:
                        # Check out logic: check if 1 minute has passed after check-in
                        time_diff = current_time - attendance.check_in_time
                        if time_diff.total_seconds() > 60:  # 1 minute after check-in
                            attendance.mark_check_out()
                            success_sound.play()
                            return f"{name}, checked out"
                        else:
                            return f"{name}, already checked in"
                    elif attendance.check_in_time and attendance.check_out_time:
                        return f"{name}, already checked out"
            
            return None
        except Exception as e:
            print(f"Error checking attendance for {name}: {e}")
            return None

    try:
        # Get all camera configurations
        cam_configs = CameraConfiguration.objects.all()
        if not cam_configs.exists():
            raise Exception("No camera configurations found. Please configure them in the admin panel.")

        # Create threads for each camera configuration
        for cam_config in cam_configs:
            stop_event = threading.Event()
            stop_events.append(stop_event)

            camera_thread = threading.Thread(target=process_frame, args=(cam_config, stop_event))
            camera_threads.append(camera_thread)
            camera_thread.start()

        # Keep the main thread running while cameras are being processed
        while any(thread.is_alive() for thread in camera_threads):
            time.sleep(1)  # Non-blocking wait, allowing for UI responsiveness

    except Exception as e:
        error_messages.append(str(e))  # Capture the error message
    finally:
        # Ensure all threads are signaled to stop
        for stop_event in stop_events:
            stop_event.set()

        # Wait for threads to finish
        for thread in camera_threads:
            thread.join(timeout=1.0)

        # Ensure all windows are closed in the main thread
        for window in camera_windows:
            try:
                if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) >= 1:
                    cv2.destroyWindow(window)
            except:
                pass  # Ignore errors if window doesn't exist

    # Check if there are any error messages
    if error_messages:
        # Join all error messages into a single string
        full_error_message = "\n".join(error_messages)
        return render(request, 'error.html', {'error_message': full_error_message})

    return redirect('emp_attendance_list')

###########################################################################

def emp_attendance_list(request):
    search_query = request.GET.get('search', '')
    date_filter = request.GET.get('attendance_date', '')

    employees = Employee.objects.all()

    if search_query:
        employees = employees.filter(name__icontains=search_query)

    employee_attendance_data = []

    for employee in employees:
        attendance_records = Attendance.objects.filter(employee=employee)

        if date_filter:
            attendance_records = attendance_records.filter(date=date_filter)

        attendance_records = attendance_records.order_by('date')

        employee_attendance_data.append({
            'employee': employee,
            'attendance_records': attendance_records
        })

    if 'download_report' in request.GET:
        # Generate and download CSV or Excel report
        return generate_attendance_report(employee_attendance_data)

    context = {
        'employee_attendance_data': employee_attendance_data,
        'search_query': search_query,
        'date_filter': date_filter
    }

    return render(request, 'emp_attendance_list.html', context)

def generate_attendance_report(employee_attendance_data):
    # Generate CSV report
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="attendance_report.csv"'

    writer = csv.writer(response)
    writer.writerow(['Employee Name', 'Employee ID', 'Attendance Date', 'Check-in Time', 'Check-out Time', 'Stayed Time'])

    for data in employee_attendance_data:
        for attendance in data['attendance_records']:
            check_in_time = attendance.check_in_time.strftime("%I:%M:%S %p") if attendance.check_in_time else 'Not Checked In'
            check_out_time = attendance.check_out_time.strftime("%I:%M:%S %p") if attendance.check_out_time else 'Not Checked Out'
            stayed_time = attendance.calculate_duration() if attendance.check_in_time and attendance.check_out_time else 'Not Checked Out'

            writer.writerow([
                data['employee'].name,
                data['employee'].employee_id,
                attendance.date,
                check_in_time,
                check_out_time,
                stayed_time
            ])
    
    return response


###############################################################


def home(request):
    return render(request, 'home.html')


# Custom user pass test for admin access
def is_admin(user):
    return user.is_superuser

@login_required
@user_passes_test(is_admin)
def employee_list(request):
    employees = Employee.objects.all()
    return render(request, 'employee_list.html', {'employees': employees})

@login_required
@user_passes_test(is_admin)
def emp_detail(request, pk):
    emp = get_object_or_404(Employee, pk=pk)
    return render(request, 'emp_detail.html', {'emp': emp})

@login_required
@user_passes_test(is_admin)
def emp_authorize(request, pk):
    emp = get_object_or_404(Employee, pk=pk)
    
    if request.method == 'POST':
        # Get the 'authorized' checkbox value and update the 'is_active' field
        authorized = request.POST.get('authorized', False)
        emp.is_active = bool(authorized)  # Update the 'is_active' field
        emp.save()
        return redirect('emp-detail', pk=pk)
    
    return render(request, 'emp_authorize.html', {'emp': emp})

# This views is for Deleting student
@login_required
@user_passes_test(is_admin)
def emp_delete(request, pk):
    emp = get_object_or_404(Employee, pk=pk)
    
    if request.method == 'POST':
        emp.delete()
        messages.success(request, 'Employee deleted successfully.')
        return redirect('employee-list')  # Redirect to the student list after deletion
    
    return render(request, 'emp_delete_confirm.html', {'emp': emp})


# View function for user login
def user_login(request):
    # Check if the request method is POST, indicating a form submission
    if request.method == 'POST':
        # Retrieve username and password from the submitted form data
        username = request.POST.get('username')
        password = request.POST.get('password')

        # Authenticate the user using the provided credentials
        user = authenticate(request, username=username, password=password)

        # Check if the user was successfully authenticated
        if user is not None:
            # Log the user in by creating a session
            login(request, user)
            # Redirect the user to the student list page after successful login
            return redirect('home')  # Replace 'student-list' with your desired redirect URL after login
        else:
            # If authentication fails, display an error message
            messages.error(request, 'Invalid username or password.')

    # Render the login template for GET requests or if authentication fails
    return render(request, 'login.html')


# This is for user logout
def user_logout(request):
    logout(request)
    return redirect('login')  # Replace 'login' with your desired redirect URL after logout

# Function to handle the creation of a new camera configuration
@login_required
@user_passes_test(is_admin)
def camera_config_create(request):
    # Check if the request method is POST, indicating form submission
    if request.method == "POST":
        # Retrieve form data from the request
        name = request.POST.get('name')
        camera_source = request.POST.get('camera_source')
        threshold = request.POST.get('threshold')

        try:
            # Save the data to the database using the CameraConfiguration model
            CameraConfiguration.objects.create(
                name=name,
                camera_source=camera_source,
                threshold=threshold,
            )
            # Redirect to the list of camera configurations after successful creation
            return redirect('camera_config_list')

        except IntegrityError:
            # Handle the case where a configuration with the same name already exists
            messages.error(request, "A configuration with this name already exists.")
            # Render the form again to allow user to correct the error
            return render(request, 'camera_config_form.html')

    # Render the camera configuration form for GET requests
    return render(request, 'camera_config_form.html')


# READ: Function to list all camera configurations
@login_required
@user_passes_test(is_admin)
def camera_config_list(request):
    # Retrieve all CameraConfiguration objects from the database
    configs = CameraConfiguration.objects.all()
    # Render the list template with the retrieved configurations
    return render(request, 'camera_config_list.html', {'configs': configs})


# UPDATE: Function to edit an existing camera configuration
@login_required
@user_passes_test(is_admin)
def camera_config_update(request, pk):
    # Retrieve the specific configuration by primary key or return a 404 error if not found
    config = get_object_or_404(CameraConfiguration, pk=pk)

    # Check if the request method is POST, indicating form submission
    if request.method == "POST":
        # Update the configuration fields with data from the form
        config.name = request.POST.get('name')
        config.camera_source = request.POST.get('camera_source')
        config.threshold = request.POST.get('threshold')
        config.success_sound_path = request.POST.get('success_sound_path')

        # Save the changes to the database
        config.save()  

        # Redirect to the list page after successful update
        return redirect('camera_config_list')  
    
    # Render the configuration form with the current configuration data for GET requests
    return render(request, 'camera_config_form.html', {'config': config})


# DELETE: Function to delete a camera configuration
@login_required
@user_passes_test(is_admin)
def camera_config_delete(request, pk):
    # Retrieve the specific configuration by primary key or return a 404 error if not found
    config = get_object_or_404(CameraConfiguration, pk=pk)

    # Check if the request method is POST, indicating confirmation of deletion
    if request.method == "POST":
        # Delete the record from the database
        config.delete()  
        # Redirect to the list of camera configurations after deletion
        return redirect('camera_config_list')

    # Render the delete confirmation template with the configuration data
    return render(request, 'camera_config_delete.html', {'config': config})
