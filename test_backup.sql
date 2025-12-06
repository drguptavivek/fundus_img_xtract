-- Test SQL backup file for database restore functionality
-- This file contains sample user data to test the upload and parsing

-- Sample users table (INSERT format - SQLAlchemy style)
INSERT INTO users (username, password_hash, full_name, email, designation, phone, is_active, created_at) VALUES
('testuser1', 'hashed_password_1', 'Test User One', 'test1@example.com', 'Doctor', '1234567890', true, NOW()),
('testuser2', 'hashed_password_2', 'Test User Two', 'test2@example.com', 'Nurse', '0987654321', true, NOW()),
('admin_user', 'hashed_password_admin', 'Admin User', 'admin@example.com', 'Administrator', '5555555555', true, NOW());

-- Sample user_roles
INSERT INTO user_roles (user_id, role_id) VALUES
(1, 1),
(2, 2),
(3, 3);

-- Sample other data
CREATE TABLE IF NOT EXISTS sample_data (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO sample_data (name, description) VALUES
('Sample Record 1', 'This is a test record'),
('Sample Record 2', 'Another test record'),
('Sample Record 3', 'Third test record');