# SHLOKA

## YOU ARE ON A MAC — Follow these exact steps:

### Step 1 — Download Python 3.14
Click the yellow button on python.org and install it.

### Step 2 — Open Terminal
Press **CMD + Space**, type **Terminal**, press Enter.

### Step 3 — Go to the shloka folder
Drag the shloka_v2 folder into the Terminal window after typing cd:
```
cd 
```
(drag folder here, then press Enter)

### Step 4 — Install packages (one time only)
```
pip3 install flask flask-sqlalchemy flask-login werkzeug python-slugify
```

### Step 5 — Run the app
```
python3 run.py
```

### Step 6 — Open browser
Go to **http://localhost:5000**

---

## Demo accounts
- Creator: admin@shloka.app / admin123  
- Learner:  demo@shloka.app  / demo123

---

## If you get "command not found: pip3"
Run this instead:
```
python3 -m pip install flask flask-sqlalchemy flask-login werkzeug python-slugify
python3 run.py
```
