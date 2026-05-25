-- Add interviewer management tables
-- Execute: psql -U postgres -d hr_system -f migrate_add_interviewers_table.sql

-- 1. Create interviewers table
CREATE TABLE IF NOT EXISTS interviewers (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    hr_user_id    UUID         NOT NULL REFERENCES hr_users(id),
    name          VARCHAR(100) NOT NULL,
    email         VARCHAR(255) NOT NULL,
    role          VARCHAR(50)  DEFAULT 'Interviewer',
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_interviewer_email ON interviewers(email);

-- 2. Create position-interviewer relationship table
CREATE TABLE IF NOT EXISTS position_interviewers (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    position_id     UUID         NOT NULL REFERENCES job_positions(id) ON DELETE CASCADE,
    interviewer_id  UUID         NOT NULL REFERENCES interviewers(id) ON DELETE CASCADE,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    
    UNIQUE(position_id, interviewer_id)
);

-- 3. Add columns to bookings table for attendee tracking
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS attendee_emails TEXT;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS attendee_names TEXT;

-- 4. Create indexes for email logs for better performance
CREATE INDEX IF NOT EXISTS idx_email_logs_booking_type ON email_logs(booking_id, email_type);
CREATE INDEX IF NOT EXISTS idx_email_logs_status ON email_logs(status);

-- 5. Initialize default interviewers (based on existing hardcoded list)
-- Note: HR admin user must already exist
INSERT INTO interviewers (hr_user_id, name, email, role, is_active)
SELECT id, 'Alice Chen', 'yukali58820@gmail.com', 'Interviewer', TRUE
FROM hr_users 
WHERE email = 'yukali58822@gmail.com' AND role = 'admin'
ON CONFLICT (email) DO NOTHING;

INSERT INTO interviewers (hr_user_id, name, email, role, is_active)
SELECT id, 'Pei Wu', 'yukali58821@gmail.com', 'Interviewer', TRUE
FROM hr_users 
WHERE email = 'yukali58822@gmail.com' AND role = 'admin'
ON CONFLICT (email) DO NOTHING;

-- 6. Verify initialization
SELECT 'Interviewers table created successfully' AS status;
SELECT COUNT(*) as interviewer_count FROM interviewers;
