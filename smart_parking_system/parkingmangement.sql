
-- ============================================================
-- SMART PARKING MANAGEMENT SYSTEM
-- COMPLETE DATABASE IMPLEMENTATION
-- MySQL 8.0.16+
-- ============================================================

CREATE DATABASE IF NOT EXISTS smart_parking;
USE smart_parking;

-- ============================================================
-- 1. ROLE TABLE
-- ============================================================

CREATE TABLE ROLE (
    Role_ID INT AUTO_INCREMENT PRIMARY KEY,
    Role_Name VARCHAR(50) NOT NULL UNIQUE,
    Description VARCHAR(255)
);

-- ============================================================
-- 2. PERMISSION TABLE
-- ============================================================

CREATE TABLE PERMISSION (
    Permission_ID INT AUTO_INCREMENT PRIMARY KEY,
    Permission_Name VARCHAR(100) NOT NULL UNIQUE,
    Description VARCHAR(255)
);

-- ============================================================
-- 3. ROLE_PERMISSION TABLE
-- ============================================================

CREATE TABLE ROLE_PERMISSION (
    Role_ID INT NOT NULL,
    Permission_ID INT NOT NULL,

    PRIMARY KEY (Role_ID, Permission_ID),

    FOREIGN KEY (Role_ID)
        REFERENCES ROLE(Role_ID)
        ON DELETE CASCADE,

    FOREIGN KEY (Permission_ID)
        REFERENCES PERMISSION(Permission_ID)
        ON DELETE CASCADE
);

-- ============================================================
-- 4. SYSTEM_USER TABLE
-- ============================================================

CREATE TABLE SYSTEM_USER (
    User_ID INT AUTO_INCREMENT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    Email VARCHAR(150) NOT NULL UNIQUE,
    Password_Hash VARCHAR(255) NOT NULL,
    Contact_Info VARCHAR(100) NOT NULL,
    Role_ID INT NOT NULL,
    Created_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (Role_ID)
        REFERENCES ROLE(Role_ID)
        ON DELETE RESTRICT
);

-- ============================================================
-- 5. OWNER TABLE
-- ============================================================

CREATE TABLE OWNER (
    Owner_ID INT AUTO_INCREMENT PRIMARY KEY,
    Owner_Name VARCHAR(100) NOT NULL,
    Contact_Info VARCHAR(100) NOT NULL,
    User_ID INT UNIQUE,

    FOREIGN KEY (User_ID)
        REFERENCES SYSTEM_USER(User_ID)
        ON DELETE SET NULL
);

-- ============================================================
-- 6. VEHICLE TABLE
-- ============================================================

CREATE TABLE VEHICLE (
    Vehicle_No VARCHAR(20) PRIMARY KEY,
    Model VARCHAR(100) NOT NULL,

    Vehicle_Type ENUM(
        'Two Wheeler',
        'Four Wheeler',
        'Other'
    ) NOT NULL,

    Owner_ID INT NOT NULL,

    FOREIGN KEY (Owner_ID)
        REFERENCES OWNER(Owner_ID)
        ON DELETE RESTRICT,

    INDEX idx_vehicle_owner (Owner_ID)
);

-- ============================================================
-- 7. PARKING_AREA TABLE
-- ============================================================

CREATE TABLE PARKING_AREA (
    Area_ID INT AUTO_INCREMENT PRIMARY KEY,
    Area_Name VARCHAR(100) NOT NULL UNIQUE,
    Location VARCHAR(255) NOT NULL,
    Description TEXT,
    Created_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 8. PARKING_SLOT TABLE
-- ============================================================

CREATE TABLE PARKING_SLOT (
    Slot_ID INT AUTO_INCREMENT PRIMARY KEY,
    Area_ID INT NOT NULL,
    Slot_Number VARCHAR(20) NOT NULL,

    Slot_Status ENUM(
        'Available',
        'Occupied',
        'Maintenance'
    ) NOT NULL DEFAULT 'Available',

    FOREIGN KEY (Area_ID)
        REFERENCES PARKING_AREA(Area_ID)
        ON DELETE RESTRICT,

    UNIQUE (Area_ID, Slot_Number),

    INDEX idx_slot_status (Slot_Status),
    INDEX idx_slot_area_status (Area_ID, Slot_Status)
);

-- ============================================================
-- 9. PARKING_RATE TABLE
-- ============================================================

CREATE TABLE PARKING_RATE (
    Rate_ID INT AUTO_INCREMENT PRIMARY KEY,

    Vehicle_Type ENUM(
        'Two Wheeler',
        'Four Wheeler',
        'Other'
    ) NOT NULL UNIQUE,

    Rate_Per_Hour DECIMAL(10,2) NOT NULL,

    Updated_At TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT chk_rate_positive
        CHECK (Rate_Per_Hour > 0)
);

-- Sample rates (change these to your actual parking prices).

INSERT INTO PARKING_RATE (Vehicle_Type, Rate_Per_Hour)
VALUES
    ('Two Wheeler', 10.00),
    ('Four Wheeler', 30.00),
    ('Other', 40.00);

-- ============================================================
-- 10. PARKING_RECORD TABLE
-- ============================================================

CREATE TABLE PARKING_RECORD (
    Record_ID INT AUTO_INCREMENT PRIMARY KEY,

    Vehicle_No VARCHAR(20) NOT NULL,
    Slot_ID INT NOT NULL,

    Entry_Time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Exit_Time DATETIME NULL,

    Duration_Hours DECIMAL(10,2) NULL,
    Amount DECIMAL(10,2) NULL,

    Record_Status ENUM(
        'Active',
        'Completed'
    ) NOT NULL DEFAULT 'Active',

    -- One active parking record per slot.

    Active_Slot_ID INT
        GENERATED ALWAYS AS (
            CASE
                WHEN Record_Status = 'Active'
                THEN Slot_ID
                ELSE NULL
            END
        ) STORED,

    -- One active parking record per vehicle.

    Active_Vehicle_No VARCHAR(20)
        GENERATED ALWAYS AS (
            CASE
                WHEN Record_Status = 'Active'
                THEN Vehicle_No
                ELSE NULL
            END
        ) STORED,

    FOREIGN KEY (Vehicle_No)
        REFERENCES VEHICLE(Vehicle_No)
        ON DELETE RESTRICT,

    FOREIGN KEY (Slot_ID)
        REFERENCES PARKING_SLOT(Slot_ID)
        ON DELETE RESTRICT,

    CONSTRAINT chk_exit_time
        CHECK (
            Exit_Time IS NULL
            OR Exit_Time >= Entry_Time
        ),

    CONSTRAINT chk_duration
        CHECK (
            Duration_Hours IS NULL
            OR Duration_Hours >= 0
        ),

    CONSTRAINT chk_record_amount
        CHECK (
            Amount IS NULL
            OR Amount >= 0
        ),

    UNIQUE (Active_Slot_ID),
    UNIQUE (Active_Vehicle_No),

    INDEX idx_record_entry (Entry_Time),
    INDEX idx_record_status (Record_Status),
    INDEX idx_record_vehicle (Vehicle_No)
);

-- ============================================================
-- 11. PAYMENT TABLE
-- ============================================================

CREATE TABLE PAYMENT (
    Payment_ID INT AUTO_INCREMENT PRIMARY KEY,

    Record_ID INT NOT NULL UNIQUE,

    Amount DECIMAL(10,2) NOT NULL,

    Payment_Method ENUM(
        'Cash',
        'UPI',
        'Card',
        'Other'
    ) NOT NULL,

    Payment_Status ENUM(
        'Pending',
        'Paid',
        'Failed',
        'Refunded'
    ) NOT NULL DEFAULT 'Pending',

    Payment_Time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (Record_ID)
        REFERENCES PARKING_RECORD(Record_ID)
        ON DELETE RESTRICT,

    CONSTRAINT chk_payment_amount
        CHECK (Amount >= 0),

    INDEX idx_payment_status (Payment_Status),
    INDEX idx_payment_time (Payment_Time)
);

-- ============================================================
-- INITIAL ROLE DATA
-- ============================================================

INSERT INTO ROLE (Role_Name, Description)
VALUES
    ('Regular User', 'Manages personal vehicles and parking'),
    ('Administrator', 'Manages the complete parking system'),
    ('Security', 'Handles vehicle entry and exit'),
    ('Parking Manager', 'Manages parking areas and slots');

-- ============================================================
-- INITIAL PERMISSION DATA
-- ============================================================

INSERT INTO PERMISSION (Permission_Name, Description)
VALUES
    ('VIEW_AVAILABILITY', 'View available parking slots'),
    ('REGISTER_VEHICLE', 'Register vehicles'),
    ('MANAGE_USERS', 'Manage system users'),
    ('MANAGE_ROLES', 'Manage roles and permissions'),
    ('MANAGE_AREAS', 'Manage parking areas'),
    ('MANAGE_SLOTS', 'Manage parking slots'),
    ('ALLOCATE_SLOT', 'Allocate parking slots'),
    ('RECORD_ENTRY', 'Record vehicle entry'),
    ('RECORD_EXIT', 'Record vehicle exit'),
    ('VIEW_HISTORY', 'View parking history'),
    ('MANAGE_PAYMENTS', 'Manage parking payments'),
    ('GENERATE_REPORTS', 'Generate parking reports');

-- ============================================================
-- ROLE AND PERMISSION MAPPING
-- ============================================================

-- Regular User permissions

INSERT INTO ROLE_PERMISSION (Role_ID, Permission_ID)
SELECT R.Role_ID, P.Permission_ID
FROM ROLE R
CROSS JOIN PERMISSION P
WHERE R.Role_Name = 'Regular User'
AND P.Permission_Name IN (
    'VIEW_AVAILABILITY',
    'REGISTER_VEHICLE',
    'VIEW_HISTORY'
);

-- Administrator permissions

INSERT INTO ROLE_PERMISSION (Role_ID, Permission_ID)
SELECT R.Role_ID, P.Permission_ID
FROM ROLE R
CROSS JOIN PERMISSION P
WHERE R.Role_Name = 'Administrator';

-- Security permissions

INSERT INTO ROLE_PERMISSION (Role_ID, Permission_ID)
SELECT R.Role_ID, P.Permission_ID
FROM ROLE R
CROSS JOIN PERMISSION P
WHERE R.Role_Name = 'Security'
AND P.Permission_Name IN (
    'VIEW_AVAILABILITY',
    'ALLOCATE_SLOT',
    'RECORD_ENTRY',
    'RECORD_EXIT',
    'VIEW_HISTORY'
);

-- Parking Manager permissions

INSERT INTO ROLE_PERMISSION (Role_ID, Permission_ID)
SELECT R.Role_ID, P.Permission_ID
FROM ROLE R
CROSS JOIN PERMISSION P
WHERE R.Role_Name = 'Parking Manager'
AND P.Permission_Name IN (
    'VIEW_AVAILABILITY',
    'MANAGE_AREAS',
    'MANAGE_SLOTS',
    'ALLOCATE_SLOT',
    'RECORD_ENTRY',
    'RECORD_EXIT',
    'VIEW_HISTORY',
    'MANAGE_PAYMENTS',
    'GENERATE_REPORTS'
);

-- ============================================================
-- VERIFICATION QUERIES
-- ============================================================

SHOW TABLES;

SELECT * FROM ROLE;

SELECT * FROM PERMISSION;

SELECT
    R.Role_Name,
    P.Permission_Name
FROM ROLE R
JOIN ROLE_PERMISSION RP
    ON R.Role_ID = RP.Role_ID
JOIN PERMISSION P
    ON RP.Permission_ID = P.Permission_ID
ORDER BY R.Role_ID, P.Permission_ID;

SELECT * FROM PARKING_RATE;

SELECT * FROM SYSTEM_USER;

SELECT * FROM OWNER;

SELECT * FROM VEHICLE;

SELECT * FROM PARKING_AREA;

SELECT * FROM PARKING_SLOT;

SELECT * FROM PARKING_RECORD;

SELECT * FROM PAYMENT;

-- ============================================================
-- END OF SMART PARKING DATABASE
-- ============================================================
