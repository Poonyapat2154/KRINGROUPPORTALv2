import os
from datetime import datetime, date
from functools import wraps
from urllib.parse import urlparse, urlunparse
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'kringroup-portal-final-secret')

database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Railway sometimes provides postgres://; SQLAlchemy wants postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'kringroup_portal.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'png', 'jpg', 'jpeg', 'gif', 'txt', 'csv'}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'warning'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), default='employee')
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    department = db.relationship('Department', backref='users')
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    @property
    def is_admin(self):
        return self.role == 'admin'

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    company = db.Column(db.String(150), nullable=False)
    contact_person = db.Column(db.String(150))
    email = db.Column(db.String(150))
    phone = db.Column(db.String(80))
    project = db.Column(db.String(180))
    status = db.Column(db.String(40), default='New')
    client_date = db.Column(db.Date, default=date.today)
    notes = db.Column(db.Text)
    file_name = db.Column(db.String(255))
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    department = db.relationship('Department', backref='clients')
    created_by = db.relationship('User', backref='clients')

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User')

class Bulletin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.relationship('User')

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    due_date = db.Column(db.Date)
    status = db.Column(db.String(40), default='Open')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    department = db.relationship('Department')

class HelpdeskTicket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(180), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(40), default='Open')
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.relationship('User')

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def log_activity(action, details=''):
    try:
        activity = Activity(action=action, details=details, user_id=current_user.id if current_user.is_authenticated else None)
        db.session.add(activity)
        db.session.commit()
    except Exception:
        db.session.rollback()

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return fn(*args, **kwargs)
    return wrapper

@app.context_processor
def inject_globals():
    unread = Activity.query.order_by(Activity.created_at.desc()).limit(5).all() if 'activity' in db.metadata.tables else []
    return {'now': datetime.utcnow(), 'recent_notifications': unread}

@app.template_filter('datefmt')
def datefmt(value):
    if not value:
        return ''
    if isinstance(value, str):
        return value
    return value.strftime('%Y-%m-%d')

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            log_activity('Logged in', f'{user.email} logged in')
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    log_activity('Logged out', f'{current_user.email} logged out')
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    clients_count = Client.query.count()
    departments_count = Department.query.count()
    employees_count = User.query.count()
    today_count = Client.query.filter(Client.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)).count()
    recent_clients = Client.query.order_by(Client.updated_at.desc()).limit(6).all()
    activities = Activity.query.order_by(Activity.created_at.desc()).limit(8).all()
    bulletins = Bulletin.query.order_by(Bulletin.created_at.desc()).limit(4).all()
    tasks = Task.query.order_by(Task.due_date.asc()).limit(5).all()
    return render_template('dashboard.html', clients_count=clients_count, departments_count=departments_count,
                           employees_count=employees_count, today_count=today_count, recent_clients=recent_clients,
                           activities=activities, bulletins=bulletins, tasks=tasks)

@app.route('/clients')
@login_required
def clients():
    q = request.args.get('q', '').strip()
    department_id = request.args.get('department_id', '')
    status = request.args.get('status', '')
    query = Client.query
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(Client.name.ilike(like), Client.company.ilike(like), Client.email.ilike(like), Client.project.ilike(like)))
    if department_id:
        query = query.filter_by(department_id=int(department_id))
    if status:
        query = query.filter_by(status=status)
    clients = query.order_by(Client.updated_at.desc()).all()
    departments = Department.query.order_by(Department.name).all()
    return render_template('clients.html', clients=clients, departments=departments, q=q, department_id=department_id, status=status)

@app.route('/clients/add', methods=['GET', 'POST'])
@login_required
def add_client():
    departments = Department.query.order_by(Department.name).all()
    if request.method == 'POST':
        file = request.files.get('file')
        filename = None
        if file and file.filename and allowed_file(file.filename):
            filename = datetime.utcnow().strftime('%Y%m%d%H%M%S_') + secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        client_date_raw = request.form.get('client_date') or date.today().isoformat()
        client = Client(
            name=request.form.get('name', '').strip(),
            company=request.form.get('company', '').strip(),
            contact_person=request.form.get('contact_person', '').strip(),
            email=request.form.get('email', '').strip(),
            phone=request.form.get('phone', '').strip(),
            project=request.form.get('project', '').strip(),
            status=request.form.get('status', 'New'),
            client_date=datetime.strptime(client_date_raw, '%Y-%m-%d').date(),
            notes=request.form.get('notes', '').strip(),
            department_id=int(request.form.get('department_id')),
            created_by_id=current_user.id,
            file_name=filename
        )
        db.session.add(client)
        db.session.commit()
        log_activity('Added client', f'{client.name} / {client.company}')
        flash('Client added successfully.', 'success')
        return redirect(url_for('clients'))
    return render_template('client_form.html', client=None, departments=departments, mode='Add')

@app.route('/clients/<int:client_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)
    departments = Department.query.order_by(Department.name).all()
    if request.method == 'POST':
        client.name = request.form.get('name', '').strip()
        client.company = request.form.get('company', '').strip()
        client.contact_person = request.form.get('contact_person', '').strip()
        client.email = request.form.get('email', '').strip()
        client.phone = request.form.get('phone', '').strip()
        client.project = request.form.get('project', '').strip()
        client.status = request.form.get('status', 'New')
        raw_date = request.form.get('client_date') or date.today().isoformat()
        client.client_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
        client.notes = request.form.get('notes', '').strip()
        client.department_id = int(request.form.get('department_id'))
        file = request.files.get('file')
        if file and file.filename and allowed_file(file.filename):
            filename = datetime.utcnow().strftime('%Y%m%d%H%M%S_') + secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            client.file_name = filename
        db.session.commit()
        log_activity('Edited client', f'{client.name} / {client.company}')
        flash('Client updated successfully.', 'success')
        return redirect(url_for('clients'))
    return render_template('client_form.html', client=client, departments=departments, mode='Edit')

@app.route('/clients/<int:client_id>/delete', methods=['POST'])
@login_required
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)
    name = client.name
    db.session.delete(client)
    db.session.commit()
    log_activity('Deleted client', name)
    flash('Client deleted.', 'success')
    return redirect(url_for('clients'))

@app.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/departments', methods=['GET', 'POST'])
@login_required
def departments():
    if request.method == 'POST':
        dept = Department(name=request.form.get('name', '').strip(), description=request.form.get('description', '').strip())
        db.session.add(dept)
        db.session.commit()
        log_activity('Added department', dept.name)
        return redirect(url_for('departments'))
    departments = Department.query.order_by(Department.name).all()
    return render_template('departments.html', departments=departments)

@app.route('/employees')
@login_required
@admin_required
def employees():
    users = User.query.order_by(User.created_at.desc()).all()
    departments = Department.query.order_by(Department.name).all()
    return render_template('employees.html', users=users, departments=departments)

@app.route('/employees/add', methods=['POST'])
@login_required
@admin_required
def add_employee():
    user = User(name=request.form.get('name'), email=request.form.get('email').lower(), role=request.form.get('role','employee'), department_id=request.form.get('department_id') or None)
    user.set_password(request.form.get('password','password123'))
    db.session.add(user)
    db.session.commit()
    log_activity('Added employee', user.email)
    flash('Employee added.', 'success')
    return redirect(url_for('employees'))

@app.route('/activity')
@login_required
def activity():
    activities = Activity.query.order_by(Activity.created_at.desc()).limit(100).all()
    return render_template('activity.html', activities=activities)

@app.route('/bulletin', methods=['GET', 'POST'])
@login_required
def bulletin():
    if request.method == 'POST':
        item = Bulletin(title=request.form.get('title'), body=request.form.get('body'), created_by_id=current_user.id)
        db.session.add(item)
        db.session.commit()
        log_activity('Posted bulletin', item.title)
        return redirect(url_for('bulletin'))
    bulletins = Bulletin.query.order_by(Bulletin.created_at.desc()).all()
    return render_template('bulletin.html', bulletins=bulletins)

@app.route('/tasks', methods=['GET', 'POST'])
@login_required
def tasks():
    departments = Department.query.order_by(Department.name).all()
    if request.method == 'POST':
        raw_due = request.form.get('due_date') or None
        task = Task(title=request.form.get('title'), department_id=request.form.get('department_id') or None,
                    due_date=datetime.strptime(raw_due, '%Y-%m-%d').date() if raw_due else None,
                    status=request.form.get('status','Open'))
        db.session.add(task)
        db.session.commit()
        log_activity('Created task', task.title)
        return redirect(url_for('tasks'))
    tasks = Task.query.order_by(Task.created_at.desc()).all()
    return render_template('tasks.html', tasks=tasks, departments=departments)

@app.route('/calendar')
@login_required
def calendar():
    clients = Client.query.order_by(Client.client_date.desc()).limit(30).all()
    tasks = Task.query.order_by(Task.due_date.desc()).limit(30).all()
    return render_template('calendar.html', clients=clients, tasks=tasks)

@app.route('/helpdesk', methods=['GET', 'POST'])
@login_required
def helpdesk():
    if request.method == 'POST':
        ticket = HelpdeskTicket(subject=request.form.get('subject'), message=request.form.get('message'), created_by_id=current_user.id)
        db.session.add(ticket)
        db.session.commit()
        log_activity('Opened helpdesk ticket', ticket.subject)
        return redirect(url_for('helpdesk'))
    tickets = HelpdeskTicket.query.order_by(HelpdeskTicket.created_at.desc()).all()
    return render_template('helpdesk.html', tickets=tickets)

@app.route('/survey')
@login_required
def survey():
    return render_template('simple_page.html', title='Feedback Survey', message='Employee polls and feedback forms can be added here.')

@app.route('/integrations')
@login_required
def integrations():
    return render_template('simple_page.html', title='Apps & Integrations', message='Future integrations: Google Drive, Microsoft Teams, email alerts, and CRM tools.')

@app.route('/settings')
@login_required
def settings():
    return render_template('simple_page.html', title='Settings', message='Customization options and widgets can be added here.')

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

@app.route('/health')
def health():
    return 'OK', 200

def seed_database():
    db.create_all()
    default_departments = ['Sales', 'Engineering', 'Finance', 'Procurement', 'HR', 'Logistics', 'IT', 'Admin']
    for name in default_departments:
        if not Department.query.filter_by(name=name).first():
            db.session.add(Department(name=name, description=f'{name} department'))
    db.session.commit()
    admin = User.query.filter_by(email='admin@kringroup.com').first()
    if not admin:
        admin_dept = Department.query.filter_by(name='Admin').first()
        admin = User(name='Admin User', email='admin@kringroup.com', role='admin', department_id=admin_dept.id if admin_dept else None)
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
    if Client.query.count() == 0:
        sales = Department.query.filter_by(name='Sales').first()
        eng = Department.query.filter_by(name='Engineering').first()
        demo_clients = [
            Client(name='John Doe', company='ABC Company', contact_person='John Doe', email='john@example.com', phone='081-234-5678', project='Client onboarding', status='New', client_date=date.today(), notes='Initial client record.', department_id=sales.id, created_by_id=admin.id),
            Client(name='Jane Smith', company='XYZ Solutions', contact_person='Jane Smith', email='jane@example.com', phone='082-111-2222', project='System support', status='In Progress', client_date=date.today(), notes='Needs department follow up.', department_id=eng.id, created_by_id=admin.id),
        ]
        db.session.add_all(demo_clients)
        db.session.add(Bulletin(title='Welcome to KRINGROUP PORTAL', body='Use this portal to share client information between departments.', created_by_id=admin.id))
        db.session.add(Activity(action='System initialized', details='Default data created.', user_id=admin.id))
        db.session.commit()

with app.app_context():
    seed_database()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
