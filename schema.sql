CREATE TABLE IF NOT EXISTS users (
    id INT NOT NULL AUTO_INCREMENT,
    client_id VARCHAR(24) DEFAULT NULL,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(150) NOT NULL,
    phone VARCHAR(30) DEFAULT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('client', 'lawyer', 'admin') NOT NULL DEFAULT 'client',
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY email (email),
    UNIQUE KEY client_id (client_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS lawyers (
    id INT NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL,
    specialization VARCHAR(150) DEFAULT NULL,
    license_number VARCHAR(100) DEFAULT NULL,
    bio TEXT,
    PRIMARY KEY (id),
    KEY user_id (user_id),
    CONSTRAINT lawyers_user_fk FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cases (
    id INT NOT NULL AUTO_INCREMENT,
    case_number VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    client_id INT NOT NULL,
    lawyer_id INT DEFAULT NULL,
    status ENUM('Pending', 'Active', 'In Progress', 'Completed', 'Closed') DEFAULT 'Pending',
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY case_number (case_number),
    KEY client_id (client_id),
    KEY lawyer_id (lawyer_id),
    CONSTRAINT cases_client_fk FOREIGN KEY (client_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT cases_lawyer_fk FOREIGN KEY (lawyer_id) REFERENCES lawyers (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_updates (
    id INT NOT NULL AUTO_INCREMENT,
    case_id INT NOT NULL,
    user_id INT NOT NULL,
    update_title VARCHAR(200) NOT NULL,
    update_description TEXT NOT NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY case_id (case_id),
    KEY user_id (user_id),
    CONSTRAINT case_updates_case_fk FOREIGN KEY (case_id) REFERENCES cases (id) ON DELETE CASCADE,
    CONSTRAINT case_updates_user_fk FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS documents (
    id INT NOT NULL AUTO_INCREMENT,
    case_id INT NOT NULL,
    uploaded_by INT NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(255) NOT NULL,
    document_type VARCHAR(100) DEFAULT NULL,
    status ENUM('Pending', 'Approved', 'Rejected') DEFAULT 'Pending',
    uploaded_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY case_id (case_id),
    KEY uploaded_by (uploaded_by),
    CONSTRAINT documents_case_fk FOREIGN KEY (case_id) REFERENCES cases (id) ON DELETE CASCADE,
    CONSTRAINT documents_user_fk FOREIGN KEY (uploaded_by) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS appointments (
    id INT NOT NULL AUTO_INCREMENT,
    case_id INT DEFAULT NULL,
    client_id INT NOT NULL,
    lawyer_id INT DEFAULT NULL,
    requested_by INT DEFAULT NULL,
    appointment_date DATETIME NOT NULL,
    subject VARCHAR(200) DEFAULT NULL,
    notes TEXT,
    status ENUM('Requested', 'Confirmed', 'Completed', 'Cancelled') DEFAULT 'Requested',
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY client_id (client_id),
    KEY lawyer_id (lawyer_id),
    CONSTRAINT appointments_client_fk FOREIGN KEY (client_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT appointments_lawyer_fk FOREIGN KEY (lawyer_id) REFERENCES lawyers (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS messages (
    id INT NOT NULL AUTO_INCREMENT,
    sender_id INT NOT NULL,
    receiver_id INT NOT NULL,
    case_id INT DEFAULT NULL,
    message TEXT NOT NULL,
    is_read TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY sender_id (sender_id),
    KEY receiver_id (receiver_id),
    KEY case_id (case_id),
    CONSTRAINT messages_sender_fk FOREIGN KEY (sender_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT messages_receiver_fk FOREIGN KEY (receiver_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT messages_case_fk FOREIGN KEY (case_id) REFERENCES cases (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document_requests (
    id INT NOT NULL AUTO_INCREMENT,
    case_id INT NOT NULL,
    client_id INT NOT NULL,
    requested_by INT NOT NULL,
    title VARCHAR(160) NOT NULL,
    instructions TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'Pending',
    fulfilled_document_id INT DEFAULT NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS legal_service_requests (
    id INT NOT NULL AUTO_INCREMENT,
    client_id INT NOT NULL,
    problem TEXT NOT NULL,
    practice_area VARCHAR(100) NOT NULL,
    urgency VARCHAR(30) NOT NULL DEFAULT 'Normal',
    attachment_name VARCHAR(255) DEFAULT NULL,
    attachment_path VARCHAR(255) DEFAULT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'Submitted',
    reviewed_by INT DEFAULT NULL,
    case_id INT DEFAULT NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME DEFAULT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
