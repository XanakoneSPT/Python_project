# Python_project

# Django Project Setup Guide

## Installation

Follow these steps to set up Django for your project:

### 1. Install Python
Ensure you have Python installed (recommended version: **Python 3.8+**).

- Check if Python is installed:
  ```sh
  python --version
  ```
- If not installed, download and install it from [Python Official Website](https://www.python.org/downloads/).

### 2. Create a Virtual Environment
It is recommended to use a virtual environment to manage dependencies.

```sh
python -m venv venv
```

Activate the virtual environment:
- **Windows:**
  ```sh
  venv\Scripts\activate
  ```
- **Mac/Linux:**
  ```sh
  source venv/bin/activate
  ```

### 3. Install Dependencies from `requirements.txt`
Ensure you have a `requirements.txt` file that contains all necessary dependencies. Then install them using:

```sh
pip install -r requirements.txt
```

### 4. Run the Development Server
```sh
python manage.py runserver
```
If successful, visit **http://127.0.0.1:8000/** in your browser.

---

## Handling Database Errors & Resetting Migrations

If you face issues related to the database (e.g., migration conflicts, missing tables), follow these steps to reset the database and migrations.

### **Step 1: Delete Migrations**
Remove existing migration files (except `__init__.py`) from each app's **migrations** folder:
```sh
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc" -delete
```
(For Windows, delete the migration files manually in `myapp/migrations/`.)

### **Step 2: Drop & Recreate the Database**
If using SQLite, delete the database file:
```sh
rm db.sqlite3  # Linux/Mac
del db.sqlite3  # Windows (Command Prompt)
```

For PostgreSQL or MySQL, manually drop and recreate the database.

### **Step 3: Reapply Migrations**
```sh
python manage.py makemigrations
python manage.py migrate
```

### **Step 4: Create a Superuser (Optional)**
```sh
python manage.py createsuperuser
```
Follow the prompts to create an admin user.

### **Step 5: Run the Server Again**
```sh
python manage.py runserver
```



### **Step 5: Run the Server Again**
```sh
python manage.py runserver
```

### Or use this username and password for admin
```sh
username: xana
password: xana1234
```

Now your Django project should be set up correctly! 🚀
