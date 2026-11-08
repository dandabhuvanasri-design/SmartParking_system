

import os
import math
import click

from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)

from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

from database import (
    get_connection,
    fetch_all,
    fetch_one,
    execute_query
)

load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "replace-this-with-a-long-random-secret"
)


# -------------------------------------------------
# DATABASE HELPER
# -------------------------------------------------

def run_transaction(callback):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        result = callback(connection, cursor)
        connection.commit()
        return result

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


# -------------------------------------------------
# LOGIN AND ROLE DECORATORS
# -------------------------------------------------

def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return wrapper


def admin_required(function):
    @wraps(function)
    @login_required
    def wrapper(*args, **kwargs):
        if session.get("role") != "Administrator":
            flash("Administrator access required.", "danger")
            return redirect(url_for("dashboard"))

        return function(*args, **kwargs)

    return wrapper


# -------------------------------------------------
# LOGIN
# -------------------------------------------------

@app.route("/")
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = fetch_one(
            """
            SELECT
                su.User_ID,
                su.Name,
                su.Email,
                su.Password_Hash,
                su.Role_ID,
                r.Role_Name
            FROM SYSTEM_USER su
            JOIN ROLE r ON su.Role_ID = r.Role_ID
            WHERE su.Email = %s
            """,
            (email,)
        )

        if user and check_password_hash(
            user["Password_Hash"], password
        ):

            session.clear()
            session["user_id"] = user["User_ID"]
            session["name"] = user["Name"]
            session["email"] = user["Email"]
            session["role"] = user["Role_Name"]

            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


# -------------------------------------------------
# REGISTRATION
# -------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        contact = request.form.get("contact", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not all([name, email, contact, password]):
            flash("Please fill in all required fields.", "warning")
            return render_template("Register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("Register.html")

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "warning")
            return render_template("Register.html")

        existing_user = fetch_one(
            "SELECT User_ID FROM SYSTEM_USER WHERE Email = %s",
            (email,)
        )

        if existing_user:
            flash("This email is already registered.", "danger")
            return render_template("Register.html")

        password_hash = generate_password_hash(password)

        def create_user(connection, cursor):

            cursor.execute(
                "SELECT Role_ID FROM ROLE WHERE Role_Name = %s",
                ("Regular User",)
            )
            role = cursor.fetchone()

            if not role:
                raise ValueError("Regular User role is missing. Check the database.")

            cursor.execute(
                """
                INSERT INTO SYSTEM_USER
                (Name, Email, Password_Hash, Contact_Info, Role_ID)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (name, email, password_hash, contact, role["Role_ID"])
            )

            user_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO OWNER
                (Owner_Name, Contact_Info, User_ID)
                VALUES (%s, %s, %s)
                """,
                (name, contact, user_id)
            )

        try:
            run_transaction(create_user)
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))

        except Exception as error:
            flash(f"Registration failed: {error}", "danger")

    return render_template("Register.html")


# -------------------------------------------------
# LOGOUT
# -------------------------------------------------

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# -------------------------------------------------
# DASHBOARD
# -------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():

    stats = fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM PARKING_AREA) AS total_areas,
            (SELECT COUNT(*) FROM PARKING_SLOT) AS total_slots,
            (SELECT COUNT(*) FROM PARKING_SLOT
             WHERE Slot_Status = 'Available') AS available_slots,
            (SELECT COUNT(*) FROM PARKING_SLOT
             WHERE Slot_Status = 'Occupied') AS occupied_slots,
            (SELECT COUNT(*) FROM VEHICLE) AS total_vehicles,
            (SELECT COUNT(*) FROM PARKING_RECORD
             WHERE Record_Status = 'Active') AS active_records
        """
    )

    if session["role"] == "Administrator":
        recent_records = fetch_all(
            """
            SELECT pr.*, v.Vehicle_No, ps.Slot_Number, pa.Area_Name,
                   o.Owner_Name
            FROM PARKING_RECORD pr
            JOIN VEHICLE v ON pr.Vehicle_No = v.Vehicle_No
            JOIN OWNER o ON v.Owner_ID = o.Owner_ID
            JOIN PARKING_SLOT ps ON pr.Slot_ID = ps.Slot_ID
            JOIN PARKING_AREA pa ON ps.Area_ID = pa.Area_ID
            ORDER BY pr.Entry_Time DESC
            LIMIT 5
            """
        )
    else:
        recent_records = fetch_all(
            """
            SELECT pr.*, v.Vehicle_No, ps.Slot_Number, pa.Area_Name
            FROM PARKING_RECORD pr
            JOIN VEHICLE v ON pr.Vehicle_No = v.Vehicle_No
            JOIN OWNER o ON v.Owner_ID = o.Owner_ID
            JOIN PARKING_SLOT ps ON pr.Slot_ID = ps.Slot_ID
            JOIN PARKING_AREA pa ON ps.Area_ID = pa.Area_ID
            WHERE o.User_ID = %s
            ORDER BY pr.Entry_Time DESC
            LIMIT 5
            """,
            (session["user_id"],)
        )

    return render_template(
        "dashboard.html",
        stats=stats,
        recent_records=recent_records
    )


# -------------------------------------------------
# PARKING AREAS
# -------------------------------------------------

@app.route("/areas", methods=["GET", "POST"])
@login_required
def areas():

    if request.method == "POST":

        if session["role"] != "Administrator":
            flash("Only administrators can add parking areas.", "danger")
            return redirect(url_for("areas"))

        area_name = request.form.get("area_name", "").strip()
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        capacity = request.form.get("capacity", "").strip()
        if not capacity.isdigit() or int(capacity) <= 0:
              flash("Please enter a valid parking capacity greater than zero.", "warning")
              return redirect(url_for("areas"))

        if not area_name or not location:
            flash("Area name and location are required.", "warning")
        else:
            try:
                execute_query(
                    """
                    INSERT INTO PARKING_AREA
                    (Area_Name, Location, Description,Capacity)
                    VALUES (%s, %s, %s,%s)
                    """,
                    (area_name, location, description,capacity)
                )
                flash("Parking area added successfully.", "success")

            except Exception as error:
                flash(f"Could not add area: {error}", "danger")

        return redirect(url_for("areas"))

    area_list = fetch_all(
        """
        SELECT pa.*,
               COUNT(ps.Slot_ID) AS Total_Slots,
               GREATEST(
                   pa.Capacity - COUNT(ps.Slot_ID), 0
                ) AS Remaining_Slots,
               SUM(CASE WHEN ps.Slot_Status = 'Available'
                   THEN 1 ELSE 0 END) AS Available_Slots
        FROM PARKING_AREA pa
        LEFT JOIN PARKING_SLOT ps ON pa.Area_ID = ps.Area_ID
        GROUP BY pa.Area_ID
        ORDER BY pa.Area_ID DESC
        """
    )

    return render_template("areas.html", areas=area_list)
@app.route("/areas/<int:area_id>/capacity", methods=["POST"])
@admin_required
def update_area_capacity(area_id):

    capacity_input = request.form.get("capacity", "").strip()

    if not capacity_input.isdigit() or int(capacity_input) <= 0:
        flash("Enter a valid capacity greater than zero.", "warning")
        return redirect(url_for("areas"))

    new_capacity = int(capacity_input)

    connection = None
    cursor = None

    try:
        connection = get_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT Capacity
            FROM PARKING_AREA
            WHERE Area_ID = %s
            FOR UPDATE
            """,
            (area_id,)
        )

        area = cursor.fetchone()

        if not area:
            raise Exception("Parking area not found.")

        cursor.execute(
            """
            SELECT COUNT(*) AS Total_Slots
            FROM PARKING_SLOT
            WHERE Area_ID = %s
            """,
            (area_id,)
        )

        result = cursor.fetchone()

        if new_capacity < result["Total_Slots"]:
            raise Exception(
                f"Capacity cannot be less than the existing "
                f"{result['Total_Slots']} slots."
            )

        cursor.execute(
            """
            UPDATE PARKING_AREA
            SET Capacity = %s
            WHERE Area_ID = %s
            """,
            (new_capacity, area_id)
        )

        connection.commit()
        flash("Parking area capacity updated successfully.", "success")

    except Exception as error:
        if connection:
            connection.rollback()

        flash(f"Could not update capacity: {error}", "danger")

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

    return redirect(url_for("areas"))


# -------------------------------------------------
# PARKING SLOTS
# -------------------------------------------------

@app.route("/slots", methods=["GET", "POST"])
@login_required
def slots():

    if request.method == "POST":

        if session["role"] != "Administrator":
            flash("Only administrators can add parking slots.", "danger")
            return redirect(url_for("slots"))

        area_id = request.form.get("area_id")
        slot_number = request.form.get("slot_number", "").strip()

        if not area_id or not slot_number:
            flash("Select an area and enter a slot number.", "warning")
        else:
            try:
                execute_query(
                    """
                    INSERT INTO PARKING_SLOT
                    (Area_ID, Slot_Number, Slot_Status)
                    VALUES (%s, %s, 'Available')
                    """,
                    (area_id, slot_number)
                )
                flash("Parking slot added successfully.", "success")

            except Exception as error:
                flash(f"Could not add slot: {error}", "danger")

        return redirect(url_for("slots"))

    slot_list = fetch_all(
        """
        SELECT ps.*, pa.Area_Name
        FROM PARKING_SLOT ps
        JOIN PARKING_AREA pa ON ps.Area_ID = pa.Area_ID
        ORDER BY pa.Area_Name, ps.Slot_Number
        """
    )

    area_list = fetch_all(
        "SELECT * FROM PARKING_AREA ORDER BY Area_Name"
    )

    return render_template(
        "slots.html",
        slots=slot_list,
        areas=area_list
    )
@app.route("/slots/bulk", methods=["POST"])
@admin_required
def bulk_add_slots():

    area_id = request.form.get("area_id", "").strip()
    quantity_input = request.form.get("quantity", "").strip()

    if not area_id.isdigit() or not quantity_input.isdigit():
        flash("Please select an area and enter a valid quantity.", "warning")
        return redirect(url_for("slots"))

    quantity = int(quantity_input)

    if quantity <= 0:
        flash("Quantity must be greater than zero.", "warning")
        return redirect(url_for("slots"))

    connection = None
    cursor = None

    try:
        connection = get_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT Capacity
            FROM PARKING_AREA
            WHERE Area_ID = %s
            FOR UPDATE
            """,
            (area_id,)
        )

        area = cursor.fetchone()

        if not area:
            raise Exception("Parking area not found.")

        cursor.execute(
            """
            SELECT Slot_Number
            FROM PARKING_SLOT
            WHERE Area_ID = %s
            """,
            (area_id,)
        )

        existing_slots = {
            row["Slot_Number"] for row in cursor.fetchall()
        }

        remaining = area["Capacity"] - len(existing_slots)

        if quantity > remaining:
            raise Exception(
                f"Only {max(remaining, 0)} slots can still be created."
            )

        new_slots = []
        number = 1

        while len(new_slots) < quantity:
            slot_number = f"A{area_id}-{number:03d}"

            if slot_number not in existing_slots:
                new_slots.append((area_id, slot_number, "Available"))

            number += 1

        cursor.executemany(
            """
            INSERT INTO PARKING_SLOT
            (Area_ID, Slot_Number, Slot_Status)
            VALUES (%s, %s, %s)
            """,
            new_slots
        )

        connection.commit()

        flash(
            f"{quantity} parking slots created successfully.",
            "success"
        )

    except Exception as error:
        if connection:
            connection.rollback()

        flash(f"Could not generate slots: {error}", "danger")

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

    return redirect(url_for("slots"))

@app.route("/slots/<int:slot_id>/status", methods=["POST"])
@admin_required
def update_slot_status(slot_id):

    new_status = request.form.get("status")

    if new_status not in ["Available", "Maintenance"]:
        flash("Invalid slot status.", "danger")
        return redirect(url_for("slots"))

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT Slot_Status FROM PARKING_SLOT WHERE Slot_ID = %s FOR UPDATE",
            (slot_id,)
        )
        slot = cursor.fetchone()

        if not slot:
            connection.rollback()
            flash("Slot not found.", "danger")
        elif slot["Slot_Status"] == "Occupied":
            connection.rollback()
            flash("An occupied slot cannot be changed.", "warning")
        else:
            cursor.execute(
                "UPDATE PARKING_SLOT SET Slot_Status = %s WHERE Slot_ID = %s",
                (new_status, slot_id)
            )
            connection.commit()
            flash("Slot status updated.", "success")

        cursor.close()
        connection.close()

    except Exception as error:
        flash(f"Could not update slot: {error}", "danger")

    return redirect(url_for("slots"))


# -------------------------------------------------
# VEHICLES
# -------------------------------------------------

@app.route("/vehicles", methods=["GET", "POST"])
@login_required
def vehicles():

    owner = fetch_one(
        "SELECT Owner_ID FROM OWNER WHERE User_ID = %s",
        (session["user_id"],)
    )

    if request.method == "POST":

        vehicle_no = request.form.get("vehicle_no", "").strip().upper()
        model = request.form.get("model", "").strip()
        vehicle_type = request.form.get("vehicle_type", "")

        if not owner:
            flash("Owner profile not found.", "danger")
            return redirect(url_for("vehicles"))

        if vehicle_type not in ["Two Wheeler", "Four Wheeler", "Other"]:
            flash("Select a valid vehicle type.", "warning")
            return redirect(url_for("vehicles"))

        try:
            execute_query(
                """
                INSERT INTO VEHICLE
                (Vehicle_No, Model, Vehicle_Type, Owner_ID)
                VALUES (%s, %s, %s, %s)
                """,
                (vehicle_no, model, vehicle_type, owner["Owner_ID"])
            )
            flash("Vehicle registered successfully.", "success")

        except Exception as error:
            flash(f"Could not register vehicle: {error}", "danger")

        return redirect(url_for("vehicles"))

    if session["role"] == "Administrator":

        vehicle_list = fetch_all(
            """
            SELECT v.*, o.Owner_Name, o.Contact_Info
            FROM VEHICLE v
            JOIN OWNER o ON v.Owner_ID = o.Owner_ID
            ORDER BY v.Vehicle_No
            """
        )

    else:

        vehicle_list = fetch_all(
            """
            SELECT v.*, o.Owner_Name
            FROM VEHICLE v
            JOIN OWNER o ON v.Owner_ID = o.Owner_ID
            WHERE o.User_ID = %s
            ORDER BY v.Vehicle_No
            """,
            (session["user_id"],)
        )

    return render_template(
        "vehicles.html",
        vehicles=vehicle_list
    )


# -------------------------------------------------
# VEHICLE ENTRY / SLOT ALLOCATION
# -------------------------------------------------

@app.route("/entry", methods=["GET", "POST"])
@login_required
def entry():

    if session["role"] == "Administrator":
        vehicle_list = fetch_all(
            "SELECT Vehicle_No, Model FROM VEHICLE ORDER BY Vehicle_No"
        )
    else:
        vehicle_list = fetch_all(
            """
            SELECT v.Vehicle_No, v.Model
            FROM VEHICLE v
            JOIN OWNER o ON v.Owner_ID = o.Owner_ID
            WHERE o.User_ID = %s
            ORDER BY v.Vehicle_No
            """,
            (session["user_id"],)
        )

    available_slots = fetch_all(
        """
        SELECT ps.Slot_ID, ps.Slot_Number, pa.Area_Name
        FROM PARKING_SLOT ps
        JOIN PARKING_AREA pa ON ps.Area_ID = pa.Area_ID
        WHERE ps.Slot_Status = 'Available'
        ORDER BY pa.Area_Name, ps.Slot_Number
        """
    )

    if request.method == "POST":

        vehicle_no = request.form.get("vehicle_no")
        slot_id = request.form.get("slot_id")

        def allocate_slot(connection, cursor):

            # Lock the selected slot to prevent simultaneous allocation.
            cursor.execute(
                """
                SELECT Slot_ID, Slot_Status
                FROM PARKING_SLOT
                WHERE Slot_ID = %s
                FOR UPDATE
                """,
                (slot_id,)
            )
            slot = cursor.fetchone()

            if not slot or slot["Slot_Status"] != "Available":
                raise ValueError("This slot is no longer available.")
            # Lock the vehicle row to prevent simultaneous
# allocation of multiple slots to the same vehicle.

            cursor.execute(
                """
                    SELECT Vehicle_No
                    FROM VEHICLE
                    WHERE Vehicle_No = %s
                    FOR UPDATE
                """,
                 (vehicle_no,)
             )

            if not cursor.fetchone():
                raise ValueError("Vehicle not found.") 

            # Check that the vehicle belongs to the logged-in user.
            if session["role"] != "Administrator":
                cursor.execute(
                    """
                    SELECT v.Vehicle_No
                    FROM VEHICLE v
                    JOIN OWNER o ON v.Owner_ID = o.Owner_ID
                    WHERE v.Vehicle_No = %s AND o.User_ID = %s
                    """,
                    (vehicle_no, session["user_id"])
                )
                if not cursor.fetchone():
                    raise ValueError("You cannot allocate a slot for this vehicle.")

            cursor.execute(
                """
                SELECT Record_ID
                FROM PARKING_RECORD
                WHERE Vehicle_No = %s AND Record_Status = 'Active'
                """,
                (vehicle_no,)
            )

            if cursor.fetchone():
                raise ValueError("This vehicle already has an active parking record.")

            cursor.execute(
                """
                INSERT INTO PARKING_RECORD
                (Vehicle_No, Slot_ID, Entry_Time, Record_Status)
                VALUES (%s, %s, NOW(), 'Active')
                """,
                (vehicle_no, slot_id)
            )

            cursor.execute(
                """
                UPDATE PARKING_SLOT
                SET Slot_Status = 'Occupied'
                WHERE Slot_ID = %s
                """,
                (slot_id,)
            )

        try:
            run_transaction(allocate_slot)
            flash("Vehicle entry recorded and slot allocated.", "success")
            return redirect(url_for("records"))

        except Exception as error:
            flash(f"Entry failed: {error}", "danger")

    return render_template(
        "entry.html",
        vehicles=vehicle_list,
        slots=available_slots
    )


# -------------------------------------------------
# PARKING RECORDS
# -------------------------------------------------

@app.route("/records")
@login_required
def records():

    if session["role"] == "Administrator":

        record_list = fetch_all(
            """
            SELECT pr.*, v.Vehicle_No, v.Model,
                   ps.Slot_Number, pa.Area_Name,
                   o.Owner_Name
            FROM PARKING_RECORD pr
            JOIN VEHICLE v ON pr.Vehicle_No = v.Vehicle_No
            JOIN OWNER o ON v.Owner_ID = o.Owner_ID
            JOIN PARKING_SLOT ps ON pr.Slot_ID = ps.Slot_ID
            JOIN PARKING_AREA pa ON ps.Area_ID = pa.Area_ID
            ORDER BY pr.Entry_Time DESC
            """
        )

    else:

        record_list = fetch_all(
            """
            SELECT pr.*, v.Vehicle_No, v.Model,
                   ps.Slot_Number, pa.Area_Name
            FROM PARKING_RECORD pr
            JOIN VEHICLE v ON pr.Vehicle_No = v.Vehicle_No
            JOIN OWNER o ON v.Owner_ID = o.Owner_ID
            JOIN PARKING_SLOT ps ON pr.Slot_ID = ps.Slot_ID
            JOIN PARKING_AREA pa ON ps.Area_ID = pa.Area_ID
            WHERE o.User_ID = %s
            ORDER BY pr.Entry_Time DESC
            """,
            (session["user_id"],)
        )

    return render_template("records.html", records=record_list)


# -------------------------------------------------
# VEHICLE EXIT AND PAYMENT
# -------------------------------------------------

@app.route("/exit/<int:record_id>", methods=["GET", "POST"])
@login_required
def exit_vehicle(record_id):

    if session["role"] == "Administrator":

        record = fetch_one(
            """
            SELECT pr.*, v.Vehicle_No, ps.Slot_Number,
                   pa.Area_Name, v.Vehicle_Type
            FROM PARKING_RECORD pr
            JOIN VEHICLE v ON pr.Vehicle_No = v.Vehicle_No
            JOIN PARKING_SLOT ps ON pr.Slot_ID = ps.Slot_ID
            JOIN PARKING_AREA pa ON ps.Area_ID = pa.Area_ID
            WHERE pr.Record_ID = %s
            """,
            (record_id,)
        )

    else:

        record = fetch_one(
            """
            SELECT pr.*, v.Vehicle_No, ps.Slot_Number,
                   pa.Area_Name, v.Vehicle_Type
            FROM PARKING_RECORD pr
            JOIN VEHICLE v ON pr.Vehicle_No = v.Vehicle_No
            JOIN OWNER o ON v.Owner_ID = o.Owner_ID
            JOIN PARKING_SLOT ps ON pr.Slot_ID = ps.Slot_ID
            JOIN PARKING_AREA pa ON ps.Area_ID = pa.Area_ID
            WHERE pr.Record_ID = %s AND o.User_ID = %s
            """,
            (record_id, session["user_id"])
        )

    if not record:
        flash("Parking record not found.", "danger")
        return redirect(url_for("records"))

    if record["Record_Status"] != "Active":
        flash("This parking record is already completed.", "warning")
        return redirect(url_for("records"))

    if request.method == "POST":

        payment_method = request.form.get("payment_method")

        if payment_method not in ["Cash", "UPI", "Card", "Other"]:
            flash("Select a valid payment method.", "warning")
            return redirect(url_for("exit_vehicle", record_id=record_id))

        def complete_parking(connection, cursor):

            cursor.execute(
                """
                SELECT pr.*, v.Vehicle_Type
                FROM PARKING_RECORD pr
                JOIN VEHICLE v ON pr.Vehicle_No = v.Vehicle_No
                WHERE pr.Record_ID = %s
                FOR UPDATE
                """,
                (record_id,)
            )
            current_record = cursor.fetchone()

            if not current_record or current_record["Record_Status"] != "Active":
                raise ValueError("This parking record has already been completed.")

            cursor.execute(
                """
                SELECT Rate_Per_Hour
                FROM PARKING_RATE
                WHERE Vehicle_Type = %s
                """,
                (current_record["Vehicle_Type"],)
            )
            rate = cursor.fetchone()

            if not rate:
                raise ValueError("Parking rate is not configured for this vehicle type.")

            cursor.execute(
                "SELECT TIMESTAMPDIFF(SECOND, Entry_Time, NOW()) AS seconds_parked FROM PARKING_RECORD WHERE Record_ID = %s",
                (record_id,)
            )
            elapsed = cursor.fetchone()["seconds_parked"] or 0

            duration_hours = max(1, math.ceil(elapsed / 3600))
            amount = duration_hours * float(rate["Rate_Per_Hour"])

            cursor.execute(
                """
                UPDATE PARKING_RECORD
                SET Exit_Time = NOW(),
                    Duration_Hours = %s,
                    Amount = %s,
                    Record_Status = 'Completed'
                WHERE Record_ID = %s
                """,
                (duration_hours, amount, record_id)
            )

            cursor.execute(
                """
                INSERT INTO PAYMENT
                (Record_ID, Amount, Payment_Method, Payment_Status, Payment_Time)
                VALUES (%s, %s, %s, 'Paid', NOW())
                """,
                (record_id, amount, payment_method)
            )

            cursor.execute(
                """
                UPDATE PARKING_SLOT
                SET Slot_Status = 'Available'
                WHERE Slot_ID = %s
                """,
                (current_record["Slot_ID"],)
            )

            return amount

        try:
            amount = run_transaction(complete_parking)
            flash(f"Vehicle exit completed. Amount paid: ₹{amount:.2f}", "success")
            return redirect(url_for("payments"))

        except Exception as error:
            flash(f"Exit failed: {error}", "danger")

    return render_template("exit.html", record=record)


# -------------------------------------------------
# PAYMENTS
# -------------------------------------------------

@app.route("/payments")
@login_required
def payments():

    if session["role"] == "Administrator":

        payment_list = fetch_all(
            """
            SELECT p.*, pr.Vehicle_No, pr.Entry_Time,
                   pr.Exit_Time, o.Owner_Name
            FROM PAYMENT p
            JOIN PARKING_RECORD pr ON p.Record_ID = pr.Record_ID
            JOIN VEHICLE v ON pr.Vehicle_No = v.Vehicle_No
            JOIN OWNER o ON v.Owner_ID = o.Owner_ID
            ORDER BY p.Payment_Time DESC
            """
        )

    else:

        payment_list = fetch_all(
            """
            SELECT p.*, pr.Vehicle_No, pr.Entry_Time, pr.Exit_Time
            FROM PAYMENT p
            JOIN PARKING_RECORD pr ON p.Record_ID = pr.Record_ID
            JOIN VEHICLE v ON pr.Vehicle_No = v.Vehicle_No
            JOIN OWNER o ON v.Owner_ID = o.Owner_ID
            WHERE o.User_ID = %s
            ORDER BY p.Payment_Time DESC
            """,
            (session["user_id"],)
        )

    return render_template("payments.html", payments=payment_list)


# -------------------------------------------------
# PARKING RATE MANAGEMENT
# -------------------------------------------------

@app.route("/rates", methods=["GET", "POST"])
@admin_required
def rates():

    if request.method == "POST":

        vehicle_type = request.form.get("vehicle_type")
        rate_value = request.form.get("rate_per_hour")

        if vehicle_type not in ["Two Wheeler", "Four Wheeler", "Other"]:
            flash("Select a valid vehicle type.", "warning")
            return redirect(url_for("rates"))

        try:
            rate_value = float(rate_value)

            if rate_value < 0:
                raise ValueError("Rate cannot be negative.")

            execute_query(
                """
                INSERT INTO PARKING_RATE
                (Vehicle_Type, Rate_Per_Hour)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE
                    Rate_Per_Hour = VALUES(Rate_Per_Hour),
                    Updated_At = CURRENT_TIMESTAMP
                """,
                (vehicle_type, rate_value)
            )

            flash("Parking rate saved successfully.", "success")

        except Exception as error:
            flash(f"Could not update rate: {error}", "danger")

        return redirect(url_for("rates"))

    rate_list = fetch_all(
        "SELECT * FROM PARKING_RATE ORDER BY Vehicle_Type"
    )

    return render_template("rates.html", rates=rate_list)


# -------------------------------------------------
# REPORTS
# -------------------------------------------------

@app.route("/reports")
@admin_required
def reports():

    summary = fetch_one(
        """
        SELECT
            COUNT(*) AS total_records,
            SUM(CASE WHEN Record_Status = 'Active'
                THEN 1 ELSE 0 END) AS active_records,
            SUM(CASE WHEN Record_Status = 'Completed'
                THEN 1 ELSE 0 END) AS completed_records,
            COALESCE(SUM(Amount), 0) AS total_revenue
        FROM PARKING_RECORD
        """
    )

    area_report = fetch_all(
        """
        SELECT pa.Area_ID, pa.Area_Name, pa.Location,
               COUNT(ps.Slot_ID) AS Total_Slots,
               SUM(CASE WHEN ps.Slot_Status = 'Available'
                   THEN 1 ELSE 0 END) AS Available_Slots,
               SUM(CASE WHEN ps.Slot_Status = 'Occupied'
                   THEN 1 ELSE 0 END) AS Occupied_Slots,
               SUM(CASE WHEN ps.Slot_Status = 'Maintenance'
                   THEN 1 ELSE 0 END) AS Maintenance_Slots
        FROM PARKING_AREA pa
        LEFT JOIN PARKING_SLOT ps ON pa.Area_ID = ps.Area_ID
        GROUP BY pa.Area_ID, pa.Area_Name, pa.Location
        ORDER BY pa.Area_Name
        """
    )

    return render_template(
        "reports.html",
        summary=summary,
        area_report=area_report
    )


# -------------------------------------------------
# CREATE ADMINISTRATOR COMMAND
# -------------------------------------------------

@app.cli.command("create-admin")
@click.option("--name", prompt="Administrator name")
@click.option("--email", prompt="Administrator email")
@click.password_option()
def create_admin(name, email, password):

    email = email.strip().lower()

    existing = fetch_one(
        "SELECT User_ID FROM SYSTEM_USER WHERE Email = %s",
        (email,)
    )

    if existing:
        click.echo("An account with this email already exists.")
        return

    password_hash = generate_password_hash(password)

    def insert_admin(connection, cursor):

        cursor.execute(
            "SELECT Role_ID FROM ROLE WHERE Role_Name = %s",
            ("Administrator",)
        )
        role = cursor.fetchone()

        if not role:
            raise ValueError("Administrator role is missing from ROLE table.")

        cursor.execute(
            """
            INSERT INTO SYSTEM_USER
            (Name, Email, Password_Hash, Contact_Info, Role_ID)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (name, email, password_hash, "Administrator", role["Role_ID"])
        )

        user_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO OWNER
            (Owner_Name, Contact_Info, User_ID)
            VALUES (%s, %s, %s)
            """,
            (name, "Administrator", user_id)
        )

    run_transaction(insert_admin)
    click.echo("Administrator account created successfully.")



# -------------------------------------------------
# RUN APPLICATION
# -------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)


