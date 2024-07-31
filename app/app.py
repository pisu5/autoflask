import os
import re
import json
import logging
from datetime import datetime
from flask import Flask, flash, redirect, render_template, request, session, url_for, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import pyrebase
import zipfile

app = Flask(__name__)
app.secret_key = "24adab94ee944cbb9ddc4017705f8593b01880da4cc383575ec8f783cafd76b0"

# Configure logging
logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Firebase configuration
firebaseConfig = {
    "apiKey": "AIzaSyDgOcQaC81a4Lt3rW1sW86BFCcuYHHEbUs",
    "authDomain": "aapurti-automation-5281b.firebaseapp.com",
    "databaseURL": "https://aapurti-automation-5281b-default-rtdb.firebaseio.com",
    "projectId": "aapurti-automation-5281b",
    "storageBucket": "aapurti-automation-5281b.appspot.com",
    "messagingSenderId": "1009745509845",
    "appId": "1:1009745509845:web:c9aadfc8c3cb8f1ba0515c",
    "measurementId": "G-JV151B2JQV"
}

# Initialize Firebase
firebase = pyrebase.initialize_app(firebaseConfig)
auth = firebase.auth()
db = firebase.database()
storage = firebase.storage()

@app.route("/")
def login():
    return render_template("login.html")

@app.route("/signup")
def signup():
    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear()  # Clear all session data
    flash("You have been logged out.")
    return redirect(url_for('login'))


@app.route("/welcome")
def welcome():
    if session.get("is_logged_in", False):
        return render_template("welcome.html", email=session["email"], name=session["name"], role=session["role"])
    else:
        return redirect(url_for('login'))

def check_password_strength(password):
    return re.match(r'^(?=.*\d)(?=.*[!@#$%^&*])(?=.*[a-z])(?=.*[A-Z]).{6,}$', password) is not None

@app.route("/result", methods=["POST", "GET"])
def result():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["pass"]
        try:
            user = auth.sign_in_with_email_and_password(email, password)
            session["is_logged_in"] = True
            session["email"] = user["email"]
            session["uid"] = user["localId"]

            data = db.child("users").get().val()
            if data and session["uid"] in data:
                session["name"] = data[session["uid"]]["name"]
                session["role"] = data[session["uid"]]["role"]
                db.child("users").child(session["uid"]).update({"last_logged_in": datetime.now().strftime("%m/%d/%Y, %H:%M:%S")})
            else:
                session["name"] = "User"
                session["role"] = "user"

            # Update bot status when logging in
            if session["role"] == "vendor":
                db.child("users").child(session["uid"]).update({"bot_status": "true"})

            if session["role"] == "admin":
                return redirect(url_for('admin_dashboard'))
            elif session["role"] == "vendor":
                return redirect(url_for('vendor_dashboard'))
            else:
                return redirect(url_for('welcome'))

        except Exception as e:
            logging.error("Error occurred during login: %s", e)
            flash("Login failed. Please check your credentials.")
            return redirect(url_for('login'))
    else:
        if session.get("is_logged_in", False):
            return redirect(url_for('welcome'))
        else:
            return redirect(url_for('login'))

@app.route("/register", methods=["POST", "GET"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["pass"]
        name = request.form["name"]
        role = "admin"  # Default role set to admin

        if not check_password_strength(password):
            flash("Password does not meet strength requirements")
            return redirect(url_for('signup'))

        try:
            user = auth.create_user_with_email_and_password(email, password)
            session["is_logged_in"] = True
            session["email"] = user["email"]
            session["uid"] = user["localId"]
            session["name"] = name
            session["role"] = role

            data = {
                "name": name,
                "email": email,
                "role": role,
                "last_logged_in": datetime.now().strftime("%m/%d/%Y, %H:%M:%S"),
                "bot_status": "false"  # Default bot status for new users
            }
            db.child("users").child(session["uid"]).set(data)
            return redirect(url_for('welcome'))
        except Exception as e:
            logging.error("Error occurred during registration: %s", e)
            flash("Error occurred while creating account")
            return redirect(url_for('signup'))
    else:
        if session.get("is_logged_in", False):
            return redirect(url_for('welcome'))
        else:
            return redirect(url_for('signup'))

@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        email = request.form["email"]
        try:
            auth.send_password_reset_email(email)
            return render_template("reset_password_done.html")
        except Exception as e:
            logging.error("Error occurred during password reset: %s", e)
            return render_template("reset_password.html", error="An error occurred. Please try again.")
    else:
        return render_template("reset_password.html")

@app.route("/create_vendor", methods=["POST"])
def create_vendor():
    if session.get("is_logged_in") and session.get("role") == "admin":
        vendor_name = request.form["vendorName"]
        vendor_email = request.form["vendorEmail"]
        vendor_password = request.form["vendorPassword"]

        if not check_password_strength(vendor_password):
            flash("Password does not meet strength requirements")
            return redirect(url_for('admin_dashboard'))

        try:
            # Create the vendor account
            user = auth.create_user_with_email_and_password(vendor_email, vendor_password)
            vendor_uid = user['localId']

            # Save vendor data in Firebase
            vendor_data = {
                "name": vendor_name,
                "email": vendor_email,
                "bot_status": "true",  # Default bot status for new vendors
                "role": "vendor",
                "last_logged_in": datetime.now().strftime("%m/%d/%Y, %H:%M:%S")
            }
            db.child("users").child(vendor_uid).set(vendor_data)

            # Prepare configuration data
            config_data = {
                "vendor_id": vendor_uid,
                "email": vendor_email,
                "some_other_config": "value"
            }
            
            # Create ZIP file with dist folder and config file
            zip_file_name = f"{vendor_uid}_package.zip"
            with zipfile.ZipFile(zip_file_name, 'w') as zipf:
                # Add the config file to the ZIP
                config_file_name = f"{vendor_uid}_config.json"
                with open(config_file_name, 'w') as config_file:
                    json.dump(config_data, config_file)
                zipf.write(config_file_name, config_file_name)
                
                # Add the dist folder to the ZIP
                current_dir = os.getcwd()  # Get the current working directory
                dist_folder_path = os.path.join(current_dir, "dist")
                for root, dirs, files in os.walk(dist_folder_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        zipf.write(file_path, os.path.relpath(file_path, dist_folder_path))
            
            # Upload the ZIP file to Firebase Cloud Storage
            storage_path = f"packages/{zip_file_name}"
            storage.child(storage_path).put(zip_file_name)
            logging.info("Uploaded ZIP file to %s.", storage_path)

            # Get the download URL for the ZIP file
            package_url = storage.child(storage_path).get_url(None)
            logging.info("ZIP file URL: %s", package_url)

            # Store the download URL in the Realtime Database under the user's node
            db.child("users").child(vendor_uid).update({"package_url": package_url})

            # Clean up the local ZIP and config file
            os.remove(zip_file_name)
            os.remove(config_file_name)
            logging.info("Local files %s and %s removed.", zip_file_name, config_file_name)

            flash("Vendor created successfully")
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            logging.error("Error occurred during vendor creation: %s", e)
            flash("Error occurred while creating vendor")
            return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('login'))

@app.route("/admin_dashboard")
def admin_dashboard():
    if session.get("is_logged_in") and session.get("role") == "admin":
        vendors = db.child("users").get().val()
        return render_template("admin_dashboard.html", vendors=vendors)
    else:
        return redirect(url_for('login'))

@app.route("/vendor_dashboard")
def vendor_dashboard():
    if session.get("is_logged_in") and session.get("role") == "vendor":
        try:
            # Fetch vendor data from Firebase using the session's UID
            vendor_data = db.child("users").child(session["uid"]).get().val()

            if vendor_data:
                name = vendor_data.get("name", "Unknown User")
                email = vendor_data.get("email", "Unknown Email")
                last_logged_in = vendor_data.get("last_logged_in", "Unknown")
                package_url = vendor_data.get("package_url", None)

                # Pass the data to the template
                return render_template("vendor_dashboard.html", 
                                       vendor_data=vendor_data, 
                                       package_url=package_url)
            else:
                flash("No data available for this user.")
                return redirect(url_for('login'))
        except Exception as e:
            flash("Error fetching user data.")
            print(f"Error: {e}")
            return redirect(url_for('login'))
    else:
        return redirect(url_for('login'))

@app.route('/update_bot_status', methods=['POST'])
def update_bot_status():
    try:
        # Parse the JSON request
        data = request.get_json()

        # Log the received data
        app.logger.info(f"Received data: {data}")

        # Extract vendor_id and bot_status
        vendor_id = data.get('vendor_id')
        bot_status = data.get('bot_status')

        # Log extracted values
        app.logger.info(f"Received vendor_id: {vendor_id}")
        app.logger.info(f"Received bot_status: {bot_status}")

        if vendor_id and bot_status is not None:
            try:
                # Fetch the vendor data from the database
                vendor_data = db.child("users").child(vendor_id).get().val()

                # Log the vendor data
                app.logger.info(f"Vendor data: {vendor_data}")

                if vendor_data:
                    # Update the bot_status field
                    db.child("users").child(vendor_id).update({'bot_status': bot_status})
                    return jsonify({'success': True}), 200
                else:
                    return jsonify({'success': False, 'message': 'Vendor not found'}), 404
            except Exception as e:
                app.logger.error(f"Error accessing or updating the database: {e}")
                return jsonify({'success': False, 'message': 'Database access error'}), 500
        else:
            return jsonify({'success': False, 'message': 'Invalid data'}), 400
    except Exception as e:
        # Log error details
        app.logger.error(f"Error updating bot status: {e}")
        return jsonify({'success': False, 'message': 'An error occurred'}), 500

if __name__ == "__main__":
    app.run(debug=True)
