-- Add applicant change audit logs for booking edits from this point onward.
CREATE TABLE IF NOT EXISTS applicant_change_logs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id      UUID        NOT NULL REFERENCES bookings(id),
    applicant_id    UUID        NOT NULL REFERENCES applicants(id),
    changed_by_type VARCHAR(20) NOT NULL CHECK (changed_by_type IN ('applicant', 'hr', 'system')),
    changed_by      UUID        REFERENCES hr_users(id),
    old_name        VARCHAR(100),
    new_name        VARCHAR(100),
    old_email       VARCHAR(255),
    new_email       VARCHAR(255),
    old_phone       VARCHAR(30),
    new_phone       VARCHAR(30),
    changed_at      TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_applicant_change_logs_changed_at
    ON applicant_change_logs (changed_at DESC);

CREATE INDEX IF NOT EXISTS idx_applicant_change_logs_booking
    ON applicant_change_logs (booking_id);
