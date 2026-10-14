JOB_PROGRESS_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS api_job_progress(
        job_id TEXT PRIMARY KEY REFERENCES api_harness_jobs(job_id) ON DELETE CASCADE,
        phase_name TEXT NOT NULL DEFAULT '',
        phase_completed INTEGER NOT NULL DEFAULT 0 CHECK(phase_completed>=0),
        phase_total INTEGER NOT NULL DEFAULT 0 CHECK(phase_total>=0),
        stage_number INTEGER NOT NULL DEFAULT 0 CHECK(stage_number BETWEEN 0 AND 2),
        child_job_id TEXT NOT NULL DEFAULT ''
    )""",
)
