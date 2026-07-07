# KRINGROUP PORTAL FINAL CLEAN

Modern clean company portal with:
- Login
- Dashboard
- Clients add/edit/delete
- Department-level organization
- Client date selection
- File upload
- IT helpdesk
- Bulletin board
- Task management
- Calendar
- Activity logs
- Employees/admin
- Railway-ready deployment

## Login
Email: `admin@kringroup.com`  
Password: `admin123`

## Run locally
```bash
python -m pip install -r requirements.txt
python app.py
```
Open: http://127.0.0.1:5000

## Railway
Upload ALL files and folders to GitHub:
- app.py
- requirements.txt
- Procfile
- runtime.txt
- templates/
- static/
- uploads/

Then deploy on Railway and generate domain in Service Settings > Networking.
